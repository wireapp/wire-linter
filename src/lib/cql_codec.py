"""CQL wire format codec encoding and decoding for the native protocol v4.

The serialization/deserialization layer of the CQL stack. Converts between Python
objects and the binary wire representation defined by the Cassandra Native Protocol
v4 specification.

Architectural layers:
    cql_types.py  defines WHAT (protocol constants, exceptions, data classes)
    cql_codec.py  defines HOW (encode/decode between Python objects and bytes)
    cql_client.py manages WHO (connection lifecycle, socket I/O)

Everything here is pure data transformation (no socket I/O, no side effects).
All functions depend only on stdlib struct and the protocol vocabulary in cql_types.py.

Encoding helpers (Python → bytes):
    _encode_string        2-byte length prefix + UTF-8
    _encode_long_string   4-byte length prefix + UTF-8
    _encode_string_map    count + N key-value [string] pairs
    _encode_bytes         4-byte signed length prefix + raw bytes

Decoding helpers (bytes → Python):
    _Reader               sequential cursor over a bytes buffer
    _build_frame          assemble a complete protocol request frame
    _read_col_type        read a column type spec (type_id + sub-types)
    _decode_value         decode a single cell value by type
    _decode_map           decode a map<K,V> from raw bytes
    _decode_collection    decode a set<T> or list<T> from raw bytes
    _parse_rows_result    parse a full RESULT Rows body into CqlResult

Connections:
    cql_client.py imports everything here to build and parse protocol frames.
"""

from __future__ import annotations

import struct

# Protocol constants and data classes no socket code in this import
from src.lib.cql_types import (
    _VERSION_REQUEST,
    _HEADER_FORMAT,
    _FLAG_GLOBAL_TABLES_SPEC,
    _FLAG_HAS_MORE_PAGES,
    _FLAG_NO_METADATA,
    _TYPE_ASCII,
    _TYPE_BIGINT,
    _TYPE_BOOLEAN,
    _TYPE_INT,
    _TYPE_VARCHAR,
    _TYPE_UUID,
    _TYPE_TIMEUUID,
    _TYPE_MAP,
    _TYPE_SET,
    _TYPE_LIST,
    CqlError,
    CqlColumn,
    CqlResult,
)


# wire format helpers

def _encode_string(value: str) -> bytes:
    """Encode a [string]: 2-byte length prefix + UTF-8."""
    encoded: bytes = value.encode('utf-8')
    return struct.pack('>H', len(encoded)) + encoded


def _encode_long_string(value: str) -> bytes:
    """Encode a [long string]: 4-byte length prefix + UTF-8."""
    encoded: bytes = value.encode('utf-8')
    return struct.pack('>i', len(encoded)) + encoded


def _encode_string_map(pairs: dict[str, str]) -> bytes:
    """Encode a [string map]: 2-byte count + count pairs of [string]."""
    parts: list[bytes] = [struct.pack('>H', len(pairs))]
    for key, val in pairs.items():
        parts.append(_encode_string(key))
        parts.append(_encode_string(val))
    return b''.join(parts)


def _encode_bytes(data: bytes) -> bytes:
    """Encode a [bytes]: 4-byte signed length prefix + raw bytes."""
    return struct.pack('>i', len(data)) + data


class _Reader:
    """Sequential reader over a bytes buffer for decoding protocol primitives."""

    def __init__(self, data: bytes) -> None:
        self._data: bytes = data
        self._pos: int = 0

    @property
    def remaining(self) -> int:
        """Number of unread bytes."""
        return len(self._data) - self._pos

    def read_raw(self, count: int) -> bytes:
        """Read exactly count raw bytes."""
        end: int = self._pos + count
        if end > len(self._data):
            raise CqlError(f"Buffer underrun: wanted {count} bytes, have {self.remaining}")
        chunk: bytes = self._data[self._pos:end]
        self._pos = end
        return chunk

    def read_int(self) -> int:
        """Read a [int] 4 bytes, signed, big-endian."""
        return struct.unpack('>i', self.read_raw(4))[0]

    def read_short(self) -> int:
        """Read a [short] 2 bytes, unsigned, big-endian."""
        return struct.unpack('>H', self.read_raw(2))[0]

    def read_byte(self) -> int:
        """Read a single byte."""
        return self.read_raw(1)[0]

    def read_string(self) -> str:
        """Read a [string] 2-byte length prefix + UTF-8."""
        length: int = self.read_short()
        return self.read_raw(length).decode('utf-8')

    def read_bytes(self) -> bytes | None:
        """Read a [bytes] 4-byte signed length prefix + data. -1 means null."""
        length: int = self.read_int()
        if length < 0:
            return None
        return self.read_raw(length)

    def read_string_from_bytes(self) -> str | None:
        """Read a [bytes] value and decode as UTF-8 string. None if null."""
        raw: bytes | None = self.read_bytes()
        if raw is None:
            return None
        return raw.decode('utf-8')


# ── Frame building ──────────────────────────────────────────────

def _build_frame(opcode: int, body: bytes, stream: int = 0) -> bytes:
    """Build a complete protocol v4 request frame."""
    header: bytes = struct.pack(
        _HEADER_FORMAT,
        _VERSION_REQUEST,   # version
        0x00,               # flags (no compression, no tracing)
        stream,             # stream id
        opcode,             # message type
        len(body),          # body length
    )
    return header + body


# ── Column type parsing ─────────────────────────────────────────

def _read_col_type(reader: _Reader) -> tuple[int, list[int]]:
    """Read a column type spec, returning (type_id, sub_type_ids).

    Collection types (map, list, set) have sub-type specs that follow
    the main type id. We read them so we can decode values correctly.
    """
    type_id: int = reader.read_short()
    sub_types: list[int] = []

    if type_id == _TYPE_MAP:
        # Map has key type + value type
        key_type: int = reader.read_short()
        val_type: int = reader.read_short()
        sub_types = [key_type, val_type]
    elif type_id in (_TYPE_LIST, _TYPE_SET):
        # List/set have a single element type
        elem_type: int = reader.read_short()
        sub_types = [elem_type]

    return type_id, sub_types


# ── Value decoding ──────────────────────────────────────────────

def _decode_value(raw: bytes | None, type_id: int, sub_types: list[int]) -> object:
    """Decode a single column value from its raw [bytes] representation.

    Only decodes types found in system_schema tables. Unknown types
    are returned as raw bytes.
    """
    if raw is None:
        return None

    # Text / ASCII / VARCHAR all UTF-8 (text and varchar share wire type 0x000D)
    if type_id in (_TYPE_VARCHAR, _TYPE_ASCII):
        return raw.decode('utf-8')

    # Integer (4 bytes, signed)
    if type_id == _TYPE_INT:
        return struct.unpack('>i', raw)[0]

    # Bigint (8 bytes, signed)
    if type_id == _TYPE_BIGINT:
        return struct.unpack('>q', raw)[0]

    # Boolean (1 byte)
    if type_id == _TYPE_BOOLEAN:
        return raw[0] != 0

    # UUID / TimeUUID (16 bytes) return as hex string
    if type_id in (_TYPE_UUID, _TYPE_TIMEUUID):
        hex_str: str = raw.hex()
        return (
            f"{hex_str[0:8]}-{hex_str[8:12]}-{hex_str[12:16]}"
            f"-{hex_str[16:20]}-{hex_str[20:32]}"
        )

    # Map<K, V> length-prefixed key-value pairs
    if type_id == _TYPE_MAP and len(sub_types) == 2:
        return _decode_map(raw, sub_types[0], sub_types[1])

    # Set<T> / List<T> length-prefixed elements
    if type_id in (_TYPE_SET, _TYPE_LIST) and len(sub_types) == 1:
        return _decode_collection(raw, sub_types[0])

    # Unknown type return raw bytes so callers can still inspect
    return raw


def _decode_map(raw: bytes, key_type: int, val_type: int) -> dict[str, object]:
    """Decode a map value from raw bytes.

    Map encoding: [int] pair_count, then for each pair:
    [bytes] key + [bytes] value.
    """
    reader: _Reader = _Reader(raw)
    count: int = reader.read_int()
    result: dict[str, object] = {}
    for _ in range(count):
        key_raw: bytes | None = reader.read_bytes()
        val_raw: bytes | None = reader.read_bytes()
        # Decode key and value using their respective sub-types
        key: object = _decode_value(key_raw, key_type, [])
        val: object = _decode_value(val_raw, val_type, [])
        result[str(key)] = val
    return result


def _decode_collection(raw: bytes, elem_type: int) -> list[object]:
    """Decode a set or list value from raw bytes.

    Encoding: [int] element_count, then for each element: [bytes] value.
    """
    reader: _Reader = _Reader(raw)
    count: int = reader.read_int()
    result: list[object] = []
    for _ in range(count):
        elem_raw: bytes | None = reader.read_bytes()
        result.append(_decode_value(elem_raw, elem_type, []))
    return result


# ── Result parsing ──────────────────────────────────────────────

def _parse_rows_result(reader: _Reader) -> CqlResult:
    """Parse a RESULT Rows body into structured CqlResult.

    Reads column metadata (names, types) then row data, decoding
    each cell according to its column type.
    """
    # Metadata flags and column count
    flags: int = reader.read_int()
    column_count: int = reader.read_int()

    # Per spec v4 §4.1.5.2: when HAS_MORE_PAGES is set, a [bytes] paging_state
    # field follows column_count before anything else discard it since we
    # issue small queries that never need paging continuation.
    if flags & _FLAG_HAS_MORE_PAGES:
        reader.read_bytes()

    # Global keyspace/table only present when GLOBAL_TABLES_SPEC is set and
    # NO_METADATA is not when NO_METADATA is set there are no column specs
    # at all, so no global prefix either.
    global_keyspace: str = ""
    global_table: str = ""
    if (flags & _FLAG_GLOBAL_TABLES_SPEC) and not (flags & _FLAG_NO_METADATA):
        global_keyspace = reader.read_string()
        global_table = reader.read_string()

    # When NO_METADATA is set, no column specs follow only row data is present.
    # Rows are still readable as raw [bytes] fields; we just have no type info.
    columns: list[CqlColumn] = []
    if not (flags & _FLAG_NO_METADATA):
        for _ in range(column_count):
            # Per-column keyspace/table only if global flag is not set
            if flags & _FLAG_GLOBAL_TABLES_SPEC:
                ks: str = global_keyspace
                tbl: str = global_table
            else:
                ks = reader.read_string()
                tbl = reader.read_string()

            col_name: str = reader.read_string()
            type_id, sub_types = _read_col_type(reader)

            columns.append(CqlColumn(
                keyspace=ks,
                table=tbl,
                name=col_name,
                type_id=type_id,
                sub_types=sub_types,
            ))

    # Read rows when NO_METADATA was set, columns is empty but the row data
    # still has column_count raw [bytes] fields per row; read them as raw bytes.
    row_count: int = reader.read_int()
    rows: list[list[object]] = []
    if flags & _FLAG_NO_METADATA:
        for _ in range(row_count):
            row: list[object] = [reader.read_bytes() for _ in range(column_count)]
            rows.append(row)
    else:
        for _ in range(row_count):
            row = []
            for col in columns:
                cell_raw: bytes | None = reader.read_bytes()
                row.append(_decode_value(cell_raw, col.type_id, col.sub_types))
            rows.append(row)

    return CqlResult(columns=columns, rows=rows)
