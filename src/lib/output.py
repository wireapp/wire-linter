"""Writes data points to a JSONL file one line at a time.

The first line is a config record (type=config) that captures the settings used
for this gathering run. Every subsequent line is a data record (type=data)
holding one collected data point.

Each line gets flushed right away so partial results survive a crash.
"""

from __future__ import annotations

import json
import sys
import threading
from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class DataPoint:
    """One collected data point. Matches the TypeScript DataPoint interface on the
    UI side (flat fields + metadata object).
    """

    # path to the data source
    path: str

    # the value (any JSON primitive)
    value: str | int | float | bool | None

    # unit of measurement (None when the target has no meaningful unit)
    unit: str | None

    # what was collected, in plain words
    description: str

    # raw command output
    raw_output: str

    # extra info (collected_at, command, duration, error, etc.)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to a plain dict for JSON serialization.

        dataclasses.asdict handles the conversion. Nested dicts like metadata
        come through as plain dicts.

        Returns:
            Dict with keys: path, value, unit, description, raw_output, metadata.
        """
        return asdict(self)


class JsonlWriter:
    """Writes JSONL, one line per data point, flushed immediately.

    Thread-safe: all writes are serialized through an internal lock so the
    writer can be called from multiple threads without interleaving lines.

    If the runner crashes mid-run, the file still has everything written so far.
    """

    def __init__(self, file_path: str) -> None:
        """Open the output file. Creates it if missing, truncates if it exists.

        Args:
            file_path: Where to write (gets created or truncated immediately).
        """
        # keep for debugging
        self._file_path: str = file_path

        # serializes all file writes so concurrent threads don't interleave
        self._lock: threading.Lock = threading.Lock()

        # once a disk write fails, skip all subsequent writes (no point retrying)
        self._write_failed: bool = False

        # open now so the file exists even if nothing gets written
        self._file = open(file_path, 'w', encoding='utf-8')

    def write_config(self, config_dict: dict[str, Any]) -> None:
        """Write the gathering config as the first JSONL line.

        This must be called before any write() calls so the config line
        is always line 1. The UI uses it to show what settings produced
        this JSONL file.

        Args:
            config_dict: The config as a plain dict (no dataclass wrappers).
        """
        # wrap in a typed envelope so the parser can distinguish it from data lines
        line: dict[str, Any] = {"type": "config", "config": config_dict}

        json_line: str = json.dumps(line, ensure_ascii=False)

        self._safe_write(json_line)

    def write(self, data_point: DataPoint) -> None:
        """Write one data point as a JSON line, then flush.

        Each line includes type=data so the parser can distinguish data
        lines from the config header.

        Args:
            data_point: The data point to write.
        """
        # add the type discriminator to the data point dict
        data: dict[str, Any] = data_point.to_dict()
        data["type"] = "data"

        # preserve utf-8
        json_line: str = json.dumps(data, ensure_ascii=False)

        self._safe_write(json_line)

    def _safe_write(self, json_line: str) -> None:
        """Write a JSON line to the file, handling disk errors gracefully.

        On first OSError (disk full, file inaccessible), logs a warning to
        stderr and sets _write_failed so subsequent writes are skipped silently.
        The runner continues collecting targets for terminal output even though
        JSONL writes have stopped.

        Args:
            json_line: A single JSON line to write (newline is appended here).
        """
        with self._lock:
            # once writes have failed, don't keep trying (same error each time)
            if self._write_failed:
                return

            try:
                self._file.write(json_line + '\n')

                # flush so partial results survive a crash
                self._file.flush()
            except OSError as exc:
                self._write_failed = True

                # warn on stderr (never stdout, that's for JSONL output)
                print(
                    f"[WARNING] JSONL write failed for {self._file_path}: {exc} "
                    f"— remaining results will not be written to disk",
                    file=sys.stderr,
                    flush=True,
                )

    def close(self) -> None:
        """Close the output file. Safe to call more than once."""
        if not self._file.closed:
            self._file.close()

    def __enter__(self) -> JsonlWriter:
        """Context manager entry, returns self."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> bool:
        """Close the file on exit. Does not suppress exceptions."""
        self.close()
        return False
