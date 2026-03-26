"""Unit tests for the JSONL output writer (src/lib/output.py)."""

import json
import os
import tempfile
import unittest
from typing import Any

from src.lib.output import DataPoint, JsonlWriter


def make_data_point(
    path: str,
    value: Any = 0,
    unit: str = "",
    description: str = "test",
    raw_output: str = "",
    metadata: dict[str, Any] | None = None,
) -> DataPoint:
    """Make a DataPoint with test defaults (avoids boilerplate).

    Args:
        path: Target path (data source identifier).
        value: Collected value.
        unit: Unit of measurement.
        description: Human-readable description.
        raw_output: Raw command output.
        metadata: Optional metadata dict (defaults to timestamp).

    Returns:
        A DataPoint instance with the given or default values.
    """
    if metadata is None:
        metadata = {"collected_at": "2026-03-11T00:00:00Z"}
    return DataPoint(
        path=path,
        value=value,
        unit=unit,
        description=description,
        raw_output=raw_output,
        metadata=metadata,
    )


class TestOutput(unittest.TestCase):
    """Test JsonlWriter and DataPoint serialization."""

    def test_jsonl_writer_format(self) -> None:
        """JSONL format has all six top-level fields."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = os.path.join(tmp_dir, "test.jsonl")
            writer = JsonlWriter(output_path)
            dp = DataPoint(
                path="host/disk_usage",
                value=55,
                unit="%",
                description="Root filesystem usage",
                raw_output="55% used",
                metadata={"collected_at": "2026-03-11T14:30:00Z"},
            )
            writer.write(dp)
            writer.close()

            with open(output_path) as f:
                line = f.readline()

            parsed = json.loads(line)

            self.assertEqual(parsed["path"], "host/disk_usage")
            self.assertEqual(parsed["value"], 55)
            self.assertEqual(parsed["unit"], "%")
            self.assertEqual(parsed["description"], "Root filesystem usage")
            self.assertEqual(parsed["raw_output"], "55% used")
            self.assertEqual(
                parsed["metadata"]["collected_at"], "2026-03-11T14:30:00Z"
            )

    def test_jsonl_incremental_write(self) -> None:
        """Each write is immediately visible before close."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = os.path.join(tmp_dir, "test.jsonl")
            writer = JsonlWriter(output_path)

            # First write file should have exactly 1 line
            writer.write(make_data_point("a"))
            with open(output_path) as f:
                self.assertEqual(len(f.readlines()), 1)

            # Second write file should have exactly 2 lines
            writer.write(make_data_point("b"))
            with open(output_path) as f:
                self.assertEqual(len(f.readlines()), 2)

            writer.close()

    def test_multiple_data_points(self) -> None:
        """Each data point has its own line with distinct paths."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = os.path.join(tmp_dir, "test.jsonl")
            writer = JsonlWriter(output_path)

            writer.write(make_data_point("a/b"))
            writer.write(make_data_point("c/d"))
            writer.write(make_data_point("e/f"))
            writer.close()

            with open(output_path) as f:
                lines = f.readlines()

            self.assertEqual(len(lines), 3)

            # Verify each line has the right path
            paths = set()
            for line in lines:
                parsed = json.loads(line)
                paths.add(parsed["path"])

            self.assertEqual(paths, {"a/b", "c/d", "e/f"})

    def test_jsonl_writer_creates_file(self) -> None:
        """File exists immediately after initialization."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = os.path.join(tmp_dir, "new_output.jsonl")

            writer = JsonlWriter(output_path)

            self.assertTrue(os.path.exists(output_path))

            writer.close()

    def test_jsonl_data_point_with_none_value(self) -> None:
        """None values serialize to JSON null."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = os.path.join(tmp_dir, "test.jsonl")
            writer = JsonlWriter(output_path)

            dp = DataPoint(
                path="test/null",
                value=None,
                unit="",
                description="test",
                raw_output="",
                metadata={},
            )
            writer.write(dp)
            writer.close()

            with open(output_path) as f:
                parsed = json.loads(f.readline())

            self.assertIsNone(parsed["value"])

    def test_jsonl_data_point_with_boolean_value(self) -> None:
        """Boolean values serialize to JSON true/false."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = os.path.join(tmp_dir, "test.jsonl")
            writer = JsonlWriter(output_path)

            dp = DataPoint(
                path="test/bool",
                value=True,
                unit="",
                description="test",
                raw_output="",
                metadata={},
            )
            writer.write(dp)
            writer.close()

            with open(output_path) as f:
                parsed = json.loads(f.readline())

            self.assertIs(parsed["value"], True)


if __name__ == '__main__':
    unittest.main()
