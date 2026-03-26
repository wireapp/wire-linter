"""Unit tests for the JSONL output writer module.

Covers DataPoint creation and serialization, JsonlWriter write/close/context
manager behavior, flush-on-write crash safety, and edge cases like empty
metadata, special characters, and None values.
"""

from __future__ import annotations

# External
import json
import os
import tempfile
from typing import Any

# Ours
from src.lib.output import DataPoint, JsonlWriter


# ---------------------------------------------------------------------------
# DataPoint creation and serialization
# ---------------------------------------------------------------------------

def test_data_point_to_dict_all_fields() -> None:
    """to_dict should return all fields as a plain dictionary."""
    # use representative values from every field to ensure none are dropped
    dp: DataPoint = DataPoint(
        path='databases/cassandra/cluster_status',
        value='UN',
        unit='status',
        description='Cassandra cluster status',
        raw_output='Datacenter: dc1\nUN 10.0.1.1',
        metadata={'collected_at': '2026-03-12 10:00:00', 'duration_seconds': 1.5},
    )

    result: dict[str, Any] = dp.to_dict()

    assert result['path'] == 'databases/cassandra/cluster_status'
    assert result['value'] == 'UN'
    assert result['unit'] == 'status'
    assert result['description'] == 'Cassandra cluster status'
    assert result['raw_output'] == 'Datacenter: dc1\nUN 10.0.1.1'
    assert result['metadata']['collected_at'] == '2026-03-12 10:00:00'
    assert result['metadata']['duration_seconds'] == 1.5


def test_data_point_to_dict_empty_metadata() -> None:
    """to_dict should work with default empty metadata."""
    # omit metadata to confirm it defaults to an empty dict, not None
    dp: DataPoint = DataPoint(
        path='test/path',
        value=42,
        unit='count',
        description='A count',
        raw_output='42',
    )

    result: dict[str, Any] = dp.to_dict()

    assert result['metadata'] == {}, f"Default metadata should be empty dict, got {result['metadata']!r}"
    assert result['value'] == 42
    assert isinstance(result['value'], int)


def test_data_point_to_dict_none_value() -> None:
    """to_dict should handle None value correctly."""
    # None value is valid when a target couldn't collect a result
    dp: DataPoint = DataPoint(
        path='test/null',
        value=None,
        unit='',
        description='No value collected',
        raw_output='',
    )

    result: dict[str, Any] = dp.to_dict()

    # None must stay None, not become 0 or empty string
    assert result['value'] is None


def test_data_point_to_dict_bool_value() -> None:
    """to_dict should preserve boolean values."""
    # Boolean True must not become int 1
    dp: DataPoint = DataPoint(
        path='test/bool',
        value=True,
        unit='',
        description='Boolean check',
        raw_output='true',
    )

    result: dict[str, Any] = dp.to_dict()

    assert result['value'] is True
    assert isinstance(result['value'], bool)


def test_data_point_to_dict_float_value() -> None:
    """to_dict should preserve float values."""
    # floats must survive the round-trip without truncation
    dp: DataPoint = DataPoint(
        path='test/float',
        value=3.14,
        unit='ratio',
        description='A ratio',
        raw_output='3.14',
    )

    result: dict[str, Any] = dp.to_dict()

    assert result['value'] == 3.14
    assert isinstance(result['value'], float)


def test_data_point_to_dict_is_json_serializable() -> None:
    """to_dict output should be JSON serializable."""
    dp: DataPoint = DataPoint(
        path='test/json',
        value='hello',
        unit='',
        description='JSON test',
        raw_output='hello',
        metadata={'key': 'value', 'nested': {'a': 1}},
    )

    # json.dumps will raise TypeError for non-serializable types
    json_str: str = json.dumps(dp.to_dict())

    # round-trip back through json.loads
    parsed: dict[str, Any] = json.loads(json_str)
    assert parsed['path'] == 'test/json'
    assert parsed['metadata']['nested']['a'] == 1


# ---------------------------------------------------------------------------
# JsonlWriter write and read back
# ---------------------------------------------------------------------------

def test_jsonl_writer_writes_single_line() -> None:
    """single DataPoint should write as one JSON line."""
    # create temp file path first so writer can open it fresh
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as tmp:
        tmp_path: str = tmp.name

    try:
        writer: JsonlWriter = JsonlWriter(tmp_path)
        dp: DataPoint = DataPoint(
            path='test/single',
            value='ok',
            unit='',
            description='Single write test',
            raw_output='ok',
        )
        writer.write(dp)
        writer.close()

        # re-open to verify data was persisted
        with open(tmp_path, 'r', encoding='utf-8') as f:
            lines: list[str] = f.readlines()

        assert len(lines) == 1, f"Expected 1 line, got {len(lines)}"
        parsed: dict[str, Any] = json.loads(lines[0])
        assert parsed['path'] == 'test/single'
        assert parsed['value'] == 'ok'
    finally:
        # clean up temp file regardless of test outcome
        os.unlink(tmp_path)


def test_jsonl_writer_writes_multiple_lines() -> None:
    """multiple DataPoints should write as separate JSON lines."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as tmp:
        tmp_path: str = tmp.name

    try:
        writer: JsonlWriter = JsonlWriter(tmp_path)

        # write three items with distinct paths/values to detect ordering issues
        for i in range(3):
            dp: DataPoint = DataPoint(
                path=f'test/multi/{i}',
                value=i,
                unit='index',
                description=f'Item {i}',
                raw_output=str(i),
            )
            writer.write(dp)

        writer.close()

        # read back all lines and verify count and content
        with open(tmp_path, 'r', encoding='utf-8') as f:
            lines: list[str] = f.readlines()

        assert len(lines) == 3, f"Expected 3 lines, got {len(lines)}"

        # each line should be valid JSON with the correct path and value
        for i, line in enumerate(lines):
            parsed: dict[str, Any] = json.loads(line)
            assert parsed['path'] == f'test/multi/{i}'
            assert parsed['value'] == i
    finally:
        os.unlink(tmp_path)


def test_jsonl_writer_context_manager() -> None:
    """JsonlWriter should work as a context manager."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as tmp:
        tmp_path: str = tmp.name

    try:
        # with-block should close the writer automatically on exit
        with JsonlWriter(tmp_path) as writer:
            dp: DataPoint = DataPoint(
                path='test/ctx',
                value='context',
                unit='',
                description='Context manager test',
                raw_output='context',
            )
            writer.write(dp)

        # file should be readable after the with-block exits
        with open(tmp_path, 'r', encoding='utf-8') as f:
            lines: list[str] = f.readlines()

        assert len(lines) == 1
        parsed: dict[str, Any] = json.loads(lines[0])
        assert parsed['path'] == 'test/ctx'
    finally:
        os.unlink(tmp_path)


def test_jsonl_writer_creates_file() -> None:
    """JsonlWriter should create the file immediately on construction."""
    # mktemp returns a path that doesn't exist yet; writer should create it
    tmp_path: str = tempfile.mktemp(suffix='.jsonl')

    try:
        # confirm precondition: file doesn't exist yet
        assert not os.path.exists(tmp_path)

        writer: JsonlWriter = JsonlWriter(tmp_path)

        # file should exist immediately after construction
        assert os.path.exists(tmp_path), "File should be created on construction"

        writer.close()
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def test_jsonl_writer_truncates_existing_file() -> None:
    """JsonlWriter should truncate existing files on construction."""
    # pre-populate file with old content that should be discarded
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as tmp:
        tmp.write('old content\n')
        tmp_path: str = tmp.name

    try:
        # opening a new writer should truncate, not append
        writer: JsonlWriter = JsonlWriter(tmp_path)
        writer.close()

        with open(tmp_path, 'r', encoding='utf-8') as f:
            content: str = f.read()

        assert content == '', f"File should be empty after truncation, got {content!r}"
    finally:
        os.unlink(tmp_path)


def test_jsonl_writer_close_idempotent() -> None:
    """calling close() multiple times should not raise."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as tmp:
        tmp_path: str = tmp.name

    try:
        writer: JsonlWriter = JsonlWriter(tmp_path)
        writer.close()

        # second close should be safe
        writer.close()
    finally:
        os.unlink(tmp_path)


def test_jsonl_writer_utf8_content() -> None:
    """UTF-8 characters in data points should be preserved."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as tmp:
        tmp_path: str = tmp.name

    try:
        # use non-ASCII characters to confirm UTF-8 encoding
        with JsonlWriter(tmp_path) as writer:
            dp: DataPoint = DataPoint(
                path='test/utf8',
                value='résultat',
                unit='°C',
                description='Température du serveur',
                raw_output='résultat: 42°C',
            )
            writer.write(dp)

        with open(tmp_path, 'r', encoding='utf-8') as f:
            parsed: dict[str, Any] = json.loads(f.readline())

        assert parsed['value'] == 'résultat'
        assert parsed['unit'] == '°C'
        assert parsed['description'] == 'Température du serveur'
    finally:
        os.unlink(tmp_path)


def test_jsonl_writer_flush_per_write() -> None:
    """data should be flushed to disk after each write."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as tmp:
        tmp_path: str = tmp.name

    try:
        writer: JsonlWriter = JsonlWriter(tmp_path)

        dp: DataPoint = DataPoint(
            path='test/flush',
            value='flushed',
            unit='',
            description='Flush test',
            raw_output='flushed',
        )
        writer.write(dp)

        # read the file while writer is open to check the OS buffer
        # was flushed immediately, not just on close
        with open(tmp_path, 'r', encoding='utf-8') as f:
            content: str = f.read()

        assert len(content) > 0, "Data should be flushed to disk before close"
        parsed: dict[str, Any] = json.loads(content.strip())
        assert parsed['path'] == 'test/flush'

        writer.close()
    finally:
        os.unlink(tmp_path)
