"""CQL protocol types, constants, and data classes.

Shared vocabulary of the CQL native protocol v4 layer: protocol constants (opcodes,
type IDs, flags, header format), exception classes, result data classes.

Extracted from cql_client.py so consumers (base_target.py, keyspaces.py, spar_tables.py,
spar_idp_count.py, cassandra_replication_factor.py) can import just the type definitions
without socket/network code.

Connections:
    cql_client.py imports everything here for the wire protocol.
    base_target.py, keyspaces.py, spar_tables.py, spar_idp_count.py,
    cassandra_replication_factor.py import CqlResult/CqlError directly.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field


# protocol constants

# request version byte for protocol v4
_VERSION_REQUEST: int = 0x04

# response version has bit 7 set
_VERSION_RESPONSE: int = 0x84

# opcodes
_OP_ERROR: int         = 0x00
_OP_STARTUP: int       = 0x01
_OP_READY: int         = 0x02
_OP_AUTHENTICATE: int  = 0x03
_OP_QUERY: int         = 0x07
_OP_RESULT: int        = 0x08
_OP_AUTH_RESPONSE: int = 0x0F
_OP_AUTH_SUCCESS: int  = 0x10

# result kinds
_RESULT_VOID: int          = 0x0001
_RESULT_ROWS: int          = 0x0002
_RESULT_SET_KEYSPACE: int  = 0x0003
_RESULT_SCHEMA_CHANGE: int = 0x0005

# metadata flags
_FLAG_GLOBAL_TABLES_SPEC: int = 0x0001
_FLAG_HAS_MORE_PAGES: int     = 0x0002
_FLAG_NO_METADATA: int         = 0x0004

# response flags (indicate prefix data prepended to body)
_RESP_FLAG_TRACING: int = 0x02
_RESP_FLAG_WARNING: int = 0x08

# consistency levels
_CONSISTENCY_ONE: int = 0x0001

# cql type IDs we decode
_TYPE_ASCII: int    = 0x0001
_TYPE_BIGINT: int   = 0x0002
_TYPE_BOOLEAN: int  = 0x0004
_TYPE_INT: int      = 0x0009
_TYPE_VARCHAR: int   = 0x000D
_TYPE_UUID: int      = 0x000C
_TYPE_TIMEUUID: int  = 0x000F
_TYPE_MAP: int       = 0x0021
_TYPE_SET: int       = 0x0022
_TYPE_LIST: int      = 0x0020

# header format: version (B), flags (B), stream (>H), opcode (B), length (>I)
_HEADER_FORMAT: str = '>BBHBI'
_HEADER_SIZE: int = struct.calcsize(_HEADER_FORMAT)  # 9 bytes


# ── Exceptions ──────────────────────────────────────────────────

class CqlError(Exception):
    """Raised when the CQL server returns an ERROR response."""
    pass


class CqlConnectionError(Exception):
    """Raised when we cannot connect or handshake with Cassandra."""
    pass


# ── Data types ──────────────────────────────────────────────────

@dataclass
class CqlColumn:
    """Metadata for a single result column."""

    keyspace: str
    table: str
    name: str
    type_id: int
    # Sub-types for collection types (map, set, list)
    sub_types: list[int] = field(default_factory=list)


@dataclass
class CqlResult:
    """Result of a CQL query column metadata plus row data."""

    columns: list[CqlColumn]
    rows: list[list[object]]

    @property
    def column_names(self) -> list[str]:
        """List of column names in result order."""
        return [col.name for col in self.columns]

    def as_dicts(self) -> list[dict[str, object]]:
        """Convert rows to a list of dicts keyed by column name."""
        names: list[str] = self.column_names
        return [dict(zip(names, row)) for row in self.rows]
