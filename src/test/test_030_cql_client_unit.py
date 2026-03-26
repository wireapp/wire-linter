"""Test the CQL native protocol client.

This covers wire format helpers, the _Reader buffer, value decoding,
CqlResult, and CqlClient (connection and queries with mocked sockets).
"""

from __future__ import annotations

import struct
from unittest.mock import patch, MagicMock

from src.lib.cql_types import (
    CqlResult,
    CqlColumn,
    CqlError,
    CqlConnectionError,
    _VERSION_REQUEST,
    _OP_STARTUP,
    _OP_READY,
    _OP_AUTHENTICATE,
    _OP_AUTH_RESPONSE,
    _OP_AUTH_SUCCESS,
    _OP_QUERY,
    _OP_RESULT,
    _OP_ERROR,
    _RESULT_ROWS,
    _RESULT_VOID,
    _TYPE_VARCHAR,
    _TYPE_INT,
    _TYPE_BIGINT,
    _TYPE_BOOLEAN,
    _TYPE_UUID,
    _TYPE_MAP,
    _TYPE_SET,
    _HEADER_FORMAT,
    _HEADER_SIZE,
)
from src.lib.cql_codec import (
    _encode_string,
    _encode_long_string,
    _encode_string_map,
    _encode_bytes,
    _Reader,
    _build_frame,
    _decode_value,
    _read_col_type,
    _parse_rows_result,
)
from src.lib.cql_client import CqlClient


# ---------------------------------------------------------------------------
# Wire format helpers
# ---------------------------------------------------------------------------

def test_encode_string() -> None:
    """Make a 2-byte length prefix + UTF-8."""
    result: bytes = _encode_string("CQL")
    assert result == b'\x00\x03CQL'


def test_encode_string_empty() -> None:
    """Handle empty strings."""
    result: bytes = _encode_string("")
    assert result == b'\x00\x00'


def test_encode_long_string() -> None:
    """Make a 4-byte signed length prefix + UTF-8."""
    result: bytes = _encode_long_string("SELECT 1")
    expected_len: bytes = struct.pack('>i', 8)
    assert result == expected_len + b'SELECT 1'


def test_encode_string_map() -> None:
    """Encode count + key-value pairs."""
    result: bytes = _encode_string_map({"CQL_VERSION": "3.0.0"})
    # 1 pair: \x00\x01 + "CQL_VERSION" (2+11) + "3.0.0" (2+5)
    assert result[:2] == b'\x00\x01'
    assert b'CQL_VERSION' in result
    assert b'3.0.0' in result


def test_encode_bytes() -> None:
    """Make a 4-byte signed length prefix + data."""
    data: bytes = b'\x00test\x00pass'
    result: bytes = _encode_bytes(data)
    expected_len: bytes = struct.pack('>i', len(data))
    assert result == expected_len + data


# ---------------------------------------------------------------------------
# _Reader
# ---------------------------------------------------------------------------

def test_reader_read_raw() -> None:
    """Read exact bytes."""
    reader: _Reader = _Reader(b'\x01\x02\x03\x04')
    assert reader.read_raw(2) == b'\x01\x02'
    assert reader.read_raw(2) == b'\x03\x04'


def test_reader_read_int() -> None:
    """Read 4-byte signed big-endian."""
    data: bytes = struct.pack('>i', -42)
    reader: _Reader = _Reader(data)
    assert reader.read_int() == -42


def test_reader_read_short() -> None:
    """Read 2-byte unsigned big-endian."""
    data: bytes = struct.pack('>H', 1024)
    reader: _Reader = _Reader(data)
    assert reader.read_short() == 1024


def test_reader_read_string() -> None:
    """Read length-prefixed UTF-8."""
    data: bytes = _encode_string("hello")
    reader: _Reader = _Reader(data)
    assert reader.read_string() == "hello"


def test_reader_read_bytes_null() -> None:
    """Return None for -1 length."""
    data: bytes = struct.pack('>i', -1)
    reader: _Reader = _Reader(data)
    assert reader.read_bytes() is None


def test_reader_read_bytes_data() -> None:
    """Read length-prefixed data."""
    payload: bytes = b'test'
    data: bytes = struct.pack('>i', 4) + payload
    reader: _Reader = _Reader(data)
    assert reader.read_bytes() == b'test'


def test_reader_remaining() -> None:
    """Report unread bytes."""
    reader: _Reader = _Reader(b'\x01\x02\x03')
    assert reader.remaining == 3
    reader.read_raw(1)
    assert reader.remaining == 2


def test_reader_buffer_underrun_raises() -> None:
    """Blow up on buffer underrun."""
    reader: _Reader = _Reader(b'\x01')
    try:
        reader.read_raw(5)
        assert False, "Expected CqlError"
    except CqlError:
        pass


# ---------------------------------------------------------------------------
# _build_frame
# ---------------------------------------------------------------------------

def test_build_frame_structure() -> None:
    """Correct header + body."""
    body: bytes = b'\x01\x02\x03'
    frame: bytes = _build_frame(_OP_QUERY, body, stream=1)

    # Parse header
    version, flags, stream, opcode, length = struct.unpack(_HEADER_FORMAT, frame[:_HEADER_SIZE])
    assert version == _VERSION_REQUEST
    assert flags == 0x00
    assert stream == 1
    assert opcode == _OP_QUERY
    assert length == 3
    assert frame[_HEADER_SIZE:] == body


# ---------------------------------------------------------------------------
# Value decoding
# ---------------------------------------------------------------------------

def test_decode_value_text() -> None:
    """Decode TEXT as UTF-8 string."""
    raw: bytes = b'hello world'
    assert _decode_value(raw, _TYPE_VARCHAR, []) == "hello world"


def test_decode_value_int() -> None:
    """Decode INT as 4-byte signed integer."""
    raw: bytes = struct.pack('>i', 42)
    assert _decode_value(raw, _TYPE_INT, []) == 42


def test_decode_value_bigint() -> None:
    """Decode BIGINT as 8-byte signed integer."""
    raw: bytes = struct.pack('>q', 9999999999)
    assert _decode_value(raw, _TYPE_BIGINT, []) == 9999999999


def test_decode_value_boolean_true() -> None:
    """Decode BOOLEAN true."""
    assert _decode_value(b'\x01', _TYPE_BOOLEAN, []) is True


def test_decode_value_boolean_false() -> None:
    """Decode BOOLEAN false."""
    assert _decode_value(b'\x00', _TYPE_BOOLEAN, []) is False


def test_decode_value_none() -> None:
    """Return None for null bytes."""
    assert _decode_value(None, _TYPE_VARCHAR, []) is None


def test_decode_value_uuid() -> None:
    """Decode UUID as formatted hex string."""
    raw: bytes = bytes(range(16))
    result: object = _decode_value(raw, _TYPE_UUID, [])
    assert isinstance(result, str)
    assert len(result) == 36  # UUID format with dashes


# ---------------------------------------------------------------------------
# CqlResult data class
# ---------------------------------------------------------------------------

def test_cql_result_column_names() -> None:
    """Return column names in order."""
    result: CqlResult = CqlResult(
        columns=[
            CqlColumn(keyspace="ks", table="t", name="col_a", type_id=_TYPE_VARCHAR),
            CqlColumn(keyspace="ks", table="t", name="col_b", type_id=_TYPE_INT),
        ],
        rows=[["val_a", 1]],
    )
    assert result.column_names == ["col_a", "col_b"]


def test_cql_result_as_dicts() -> None:
    """Convert rows to dicts."""
    result: CqlResult = CqlResult(
        columns=[
            CqlColumn(keyspace="ks", table="t", name="name", type_id=_TYPE_VARCHAR),
            CqlColumn(keyspace="ks", table="t", name="age", type_id=_TYPE_INT),
        ],
        rows=[["alice", 30], ["bob", 25]],
    )
    dicts: list[dict[str, object]] = result.as_dicts()
    assert len(dicts) == 2
    assert dicts[0] == {"name": "alice", "age": 30}
    assert dicts[1] == {"name": "bob", "age": 25}


def test_cql_result_empty() -> None:
    """Handle empty rows."""
    result: CqlResult = CqlResult(columns=[], rows=[])
    assert result.column_names == []
    assert result.as_dicts() == []


# ---------------------------------------------------------------------------
# CqlClient connection and query (mocked socket)
# ---------------------------------------------------------------------------

def _make_response_frame(opcode: int, body: bytes = b'') -> bytes:
    """Build a mocked CQL response frame (version 0x84)."""
    header: bytes = struct.pack(
        _HEADER_FORMAT,
        0x84,       # response version
        0x00,       # flags
        0,          # stream
        opcode,     # opcode
        len(body),  # body length
    )
    return header + body


def test_cql_client_connect_ready() -> None:
    """Connect succeeds when server sends READY."""
    ready_frame: bytes = _make_response_frame(_OP_READY)

    mock_sock: MagicMock = MagicMock()
    # recv needs to return header first, then body (which is empty for READY)
    # _recv_exact reads in a loop, so we return the full header at once
    mock_sock.recv.side_effect = lambda n: ready_frame[:n] if n == _HEADER_SIZE else b''

    with patch("src.lib.cql_client.socket.create_connection", return_value=mock_sock):
        client: CqlClient = CqlClient("127.0.0.1", port=9042)
        client.connect()

    mock_sock.sendall.assert_called_once()
    client.close()


def test_cql_client_connect_error_raises() -> None:
    """Raise CqlConnectionError when TCP fails."""
    with patch("src.lib.cql_client.socket.create_connection", side_effect=ConnectionRefusedError("refused")):
        client: CqlClient = CqlClient("127.0.0.1", port=9042)
        try:
            client.connect()
            assert False, "Expected CqlConnectionError"
        except CqlConnectionError:
            pass


def test_cql_client_query_not_connected_raises() -> None:
    """Raise when not connected."""
    client: CqlClient = CqlClient("127.0.0.1")
    try:
        client.query("SELECT 1")
        assert False, "Expected CqlConnectionError"
    except CqlConnectionError:
        pass


def test_cql_client_close_idempotent() -> None:
    """Safe to call close multiple times."""
    client: CqlClient = CqlClient("127.0.0.1")
    client.close()
    client.close()  # Should not raise


def test_cql_client_context_manager() -> None:
    """Work as a context manager (auto cleanup)."""
    ready_frame: bytes = _make_response_frame(_OP_READY)

    mock_sock: MagicMock = MagicMock()
    mock_sock.recv.side_effect = lambda n: ready_frame[:n] if n == _HEADER_SIZE else b''

    with patch("src.lib.cql_client.socket.create_connection", return_value=mock_sock):
        with CqlClient("127.0.0.1") as client:
            assert client._sock is not None

    # After context exit, socket should be closed
    mock_sock.close.assert_called()


def test_cql_client_parse_error() -> None:
    """Extract error code and message."""
    error_body: bytes = struct.pack('>i', 0x2200) + _encode_string("Invalid query")
    result: str = CqlClient._parse_error(error_body)
    assert "0x2200" in result
    assert "Invalid query" in result


def test_cql_client_parse_error_short_body() -> None:
    """Handle short bodies without crashing."""
    result: str = CqlClient._parse_error(b'\x01\x02')
    assert "unparseable" in result
