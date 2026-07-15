"""Build bounded CSV files for the local API runtime.

The downloaded observation files are intentionally kept as the full archive.
Rows are grouped by station/year rather than globally sorted, so this script
streams every row and copies the common recent period into ``data/runtime``.
"""

from __future__ import annotations

import argparse
import json
import mmap
import os
from datetime import datetime, timedelta
from pathlib import Path


DATA_DIR = Path(__file__).resolve().parent
RUNTIME_DIR = DATA_DIR / "runtime"
DT_FMT = "%Y-%m-%d %H:%M:%S"
DT_BYTES = 19


def observation_sources() -> list[Path]:
    return sorted(path for path in DATA_DIR.glob("observations*.csv") if path.is_file())


def _header_end(data: mmap.mmap) -> int:
    newline = data.find(b"\n")
    if newline < 0:
        raise ValueError("CSV header is missing")
    return newline + 1


def _line_timestamp(data: mmap.mmap, start: int) -> str:
    raw = data[start : start + DT_BYTES]
    try:
        value = raw.decode("ascii")
        datetime.strptime(value, DT_FMT)
    except (UnicodeDecodeError, ValueError) as ex:
        raise ValueError(f"invalid datetime at byte {start}: {raw!r}") from ex
    return value


def latest_timestamp(path: Path) -> str:
    with path.open("rb") as src, mmap.mmap(src.fileno(), 0, access=mmap.ACCESS_READ) as data:
        data_start = _header_end(data)
        end = len(data)
        while end > data_start and data[end - 1] in b"\r\n":
            end -= 1
        if end <= data_start:
            raise ValueError(f"no observation rows: {path}")
        start = data.rfind(b"\n", data_start, end) + 1
        return _line_timestamp(data, start)


def write_runtime_file(source: Path, destination: Path, cutoff: str, end: str) -> dict:
    """Filter by the leading datetime without assuming global row ordering."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    cutoff_bytes = cutoff.encode("ascii")
    end_bytes = end.encode("ascii")
    row_count = 0

    try:
        with source.open("rb", buffering=16 * 1024 * 1024) as src:
            header = src.readline()
            with temporary.open("wb", buffering=16 * 1024 * 1024) as dst:
                dst.write(header)
                for line in src:
                    timestamp = line[:DT_BYTES]
                    if cutoff_bytes <= timestamp <= end_bytes:
                        dst.write(line)
                        row_count += 1
                dst.flush()
                os.fsync(dst.fileno())
        os.replace(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise

    return {
        "source": source.name,
        "output": destination.name,
        "source_bytes": source.stat().st_size,
        "output_bytes": destination.stat().st_size,
        "latest": latest_timestamp(source),
        "rows": row_count,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build recent observation CSVs for server.py")
    parser.add_argument("--days", type=int, default=365, help="number of recent days to retain")
    args = parser.parse_args()
    if args.days < 1:
        parser.error("--days must be at least 1")

    sources = observation_sources()
    if not sources:
        raise RuntimeError(f"no observations*.csv files found in {DATA_DIR}")

    latest_by_file = {path: latest_timestamp(path) for path in sources}
    common_latest = min(
        datetime.strptime(value, DT_FMT) for value in latest_by_file.values()
    )
    cutoff = (common_latest - timedelta(days=args.days)).strftime(DT_FMT)
    end = common_latest.strftime(DT_FMT)

    print(f"common_latest={end} cutoff={cutoff} days={args.days}")
    files = []
    for source in sources:
        destination = RUNTIME_DIR / source.name
        print(f"extracting {source.name} -> {destination.relative_to(DATA_DIR)}")
        result = write_runtime_file(source, destination, cutoff, end)
        files.append(result)
        print(f"  {result['rows']} rows, {result['output_bytes'] / 1024 / 1024:.1f} MiB")

    manifest = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "days": args.days,
        "latest": end,
        "cutoff": cutoff,
        "files": files,
    }
    manifest_path = RUNTIME_DIR / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {manifest_path}")


if __name__ == "__main__":
    main()
