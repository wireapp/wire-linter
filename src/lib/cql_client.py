"""Minimal CQL client speaking Cassandra Native Protocol v4.

Pure Python, zero dependencies (just socket and struct from stdlib).
Supports enough protocol to run read-only queries against system tables
(keyspace listing, replication strategy).

Protocol reference:
    https://github.com/apache/cassandra/blob/trunk/doc/native_protocol_v4.spec

Frame layout (9-byte header):
    version (1B) | flags (1B) | stream (2B) | opcode (1B) | length (4B) | body

Implemented opcodes:
    Request:  STARTUP (0x01), AUTH_RESPONSE (0x0F), QUERY (0x07)
    Response: READY (0x02), AUTHENTICATE (0x03), AUTH_SUCCESS (0x10),
              RESULT (0x08), ERROR (0x00)

Connections:
    ssh.py SSHTunnel provides the local forwarded port.
    base_target.py run_cql_query() orchestrates tunnel + client.
"""

from __future__ import annotations

import socket
import struct

# Protocol constants, exceptions, and data classes live in their own module
# so consumers that only need type definitions don't pull in socket/network code.
from src.lib.cql_types import (
    _OP_ERROR,
    _OP_STARTUP,
    _OP_READY,
    _OP_AUTHENTICATE,
    _OP_QUERY,
    _OP_RESULT,
    _OP_AUTH_RESPONSE,
    _OP_AUTH_SUCCESS,
    _RESULT_VOID,
    _RESULT_ROWS,
    _RESULT_SET_KEYSPACE,
    _RESULT_SCHEMA_CHANGE,
    _RESP_FLAG_TRACING,
    _RESP_FLAG_WARNING,
    _CONSISTENCY_ONE,
    _HEADER_FORMAT,
    _HEADER_SIZE,
    CqlError,
    CqlConnectionError,
    CqlResult,
)

# Wire format codec encoding/decoding between Python objects and CQL bytes
from src.lib.cql_codec import (
    _Reader,
    _encode_string_map,
    _encode_long_string,
    _encode_bytes,
    _build_frame,
    _parse_rows_result,
)


# socket I/O helpers

def _recv_exact(sock: socket.socket, count: int) -> bytes:
    """Read exactly count bytes from a socket (raise on premature close)."""
    chunks: list[bytes] = []
    received: int = 0
    while received < count:
        chunk: bytes = sock.recv(count - received)
        if not chunk:
            raise CqlConnectionError(
                f"Connection closed after {received}/{count} bytes"
            )
        chunks.append(chunk)
        received += len(chunk)
    return b''.join(chunks)


def _recv_frame(sock: socket.socket) -> tuple[int, bytes]:
    """Receive a complete response frame, returning (opcode, body).

    Strips protocol-level prefix data (tracing UUID, warning strings) from the body
    when response flags are set. Cassandra sets WARNING on queries like SELECT COUNT(*)
    without partition key, prepending a string list to the body that gets skipped.
    """
    header_bytes: bytes = _recv_exact(sock, _HEADER_SIZE)
    _version, flags, _stream, opcode, body_length = struct.unpack(
        _HEADER_FORMAT, header_bytes,
    )
    body: bytes = _recv_exact(sock, body_length) if body_length > 0 else b''

    # strip prefix data that Cassandra prepends based on response flags
    offset: int = 0

    # tracing flag: 16-byte UUID prepended to body
    if flags & _RESP_FLAG_TRACING:
        offset += 16

    # warning flag: [string list] prepended (2-byte count, then each string
    # is 2-byte length + UTF-8 bytes)
    if flags & _RESP_FLAG_WARNING and len(body) >= offset + 2:
        reader: _Reader = _Reader(body[offset:])
        warning_count: int = reader.read_short()
        for _ in range(warning_count):
            # each warning is a [string]: 2-byte length + data
            warning_len: int = reader.read_short()
            reader.read_raw(warning_len)
        # advance offset past all warning data
        offset += (len(body[offset:]) - reader.remaining)

    # return body with prefix data stripped
    if offset > 0:
        body = body[offset:]

    return opcode, body


# client

class CqlClient:
    """Minimal CQL client for querying Cassandra over the native protocol.

    Handles the STARTUP handshake (with optional password authentication), then
    lets you run queries and get structured results. Designed for simple read-only
    diagnostic queries against system tables.

    Usage:
        client = CqlClient("127.0.0.1", port=9042)
        client.connect()
        result = client.query("SELECT keyspace_name, replication FROM system_schema.keyspaces")
        for row in result.as_dicts():
            print(row["keyspace_name"], row["replication"])
        client.close()

    Or as a context manager:
        with CqlClient("127.0.0.1") as client:
            result = client.query("SELECT ...")
    """

    def __init__(
        self,
        host: str = '127.0.0.1',
        port: int = 9042,
        username: str | None = None,
        password: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        """Initialize client parameters (does not connect yet).

        Args:
            host:     Cassandra host to connect to.
            port:     CQL native protocol port (default 9042).
            username: Optional username for PasswordAuthenticator.
            password: Optional password for PasswordAuthenticator.
            timeout:  Socket timeout in seconds.
        """
        self._host: str = host
        self._port: int = port
        self._username: str | None = username
        self._password: str | None = password
        self._timeout: float = timeout
        self._sock: socket.socket | None = None

    def connect(self) -> None:
        """Open TCP connection and perform the CQL handshake.

        Sends STARTUP, handles READY or AUTHENTICATE + AUTH_RESPONSE, leaves
        the connection ready for queries.

        Raises:
            CqlConnectionError: If connection or handshake fails.
            CqlError: If the server returns an ERROR response.
        """
        try:
            self._sock = socket.create_connection(
                (self._host, self._port),
                timeout=self._timeout,
            )
        except (OSError, ConnectionRefusedError) as exc:
            raise CqlConnectionError(
                f"Cannot connect to {self._host}:{self._port}: {exc}"
            ) from exc

        # wrap entire handshake so any failure closes the socket.
        # python doesn't call __exit__ when __enter__ raises, so without this
        # try/except the socket would leak whenever handshake fails.
        try:
            # send STARTUP with required CQL_VERSION
            startup_body: bytes = _encode_string_map({"CQL_VERSION": "3.0.0"})
            self._sock.sendall(_build_frame(_OP_STARTUP, startup_body))

            # read handshake response
            opcode, body = _recv_frame(self._sock)

            if opcode == _OP_READY:
                # no auth required, connection is ready
                return

            if opcode == _OP_AUTHENTICATE:
                # server requires authentication (_handle_auth may also raise)
                self._handle_auth()
                return

            if opcode == _OP_ERROR:
                raise CqlError(f"Handshake error: {self._parse_error(body)}")

            raise CqlConnectionError(f"Unexpected handshake opcode: 0x{opcode:02x}")
        except Exception:
            # ensure socket is released on any handshake failure (no file descriptor leak)
            self.close()
            raise

    def _handle_auth(self) -> None:
        """Complete SASL PLAIN authentication after receiving AUTHENTICATE.

        Sends AUTH_RESPONSE with «\\x00username\\x00password» encoding.

        Raises:
            CqlConnectionError: If no credentials provided.
            CqlError: If authentication fails.
        """
        if not self._username or not self._password:
            raise CqlConnectionError("Authentication required but no credentials provided")

        username: str = self._username
        password: str = self._password

        if self._sock is None:
            raise CqlConnectionError("_handle_auth called without active socket")

        # sasl plain: \x00<username>\x00<password>
        sasl_payload: bytes = b'\x00' + username.encode('utf-8') + b'\x00' + password.encode('utf-8')
        auth_body: bytes = _encode_bytes(sasl_payload)
        self._sock.sendall(_build_frame(_OP_AUTH_RESPONSE, auth_body))

        opcode, body = _recv_frame(self._sock)

        if opcode == _OP_AUTH_SUCCESS:
            return

        if opcode == _OP_ERROR:
            raise CqlError(f"Authentication failed: {self._parse_error(body)}")

        raise CqlConnectionError(f"Unexpected auth response opcode: 0x{opcode:02x}")

    def query(self, cql: str) -> CqlResult:
        """Execute a CQL query and return structured results.

        Args:
            cql: The CQL query string.

        Returns:
            A CqlResult with columns and rows.

        Raises:
            CqlError: If the server returns an ERROR or unexpected result kind.
            CqlConnectionError: If the connection is not open.
        """
        if self._sock is None:
            raise CqlConnectionError("Not connected - call connect() first")

        # QUERY body: [long string] query + [short] consistency + [byte] flags
        query_body: bytes = (
            _encode_long_string(cql)
            + struct.pack('>H', _CONSISTENCY_ONE)  # consistency = ONE
            + struct.pack('B', 0x00)               # no query flags
        )
        self._sock.sendall(_build_frame(_OP_QUERY, query_body))

        opcode, body = _recv_frame(self._sock)

        if opcode == _OP_ERROR:
            raise CqlError(f"Query error: {self._parse_error(body)}")

        if opcode != _OP_RESULT:
            raise CqlError(f"Unexpected query response opcode: 0x{opcode:02x}")

        reader: _Reader = _Reader(body)
        result_kind: int = reader.read_int()

        if result_kind == _RESULT_ROWS:
            return _parse_rows_result(reader)

        if result_kind == _RESULT_VOID:
            return CqlResult(columns=[], rows=[])

        if result_kind == _RESULT_SET_KEYSPACE:
            return CqlResult(columns=[], rows=[])

        if result_kind == _RESULT_SCHEMA_CHANGE:
            return CqlResult(columns=[], rows=[])

        raise CqlError(f"Unsupported result kind: 0x{result_kind:04x}")

    def close(self) -> None:
        """Close the TCP connection."""
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def __enter__(self) -> CqlClient:
        """Context manager entry connect and return self."""
        self.connect()
        return self

    def __exit__(self, *_args: object) -> None:
        """Context manager exit close connection."""
        self.close()

    @staticmethod
    def _parse_error(body: bytes) -> str:
        """Extract human-readable error message from an ERROR response body.

        ERROR body: [int] error_code + [string] message.
        """
        if len(body) < 6:
            return f"(unparseable error, {len(body)} bytes)"
        reader: _Reader = _Reader(body)
        error_code: int = reader.read_int()
        message: str = reader.read_string()
        return f"[0x{error_code:04x}] {message}"
