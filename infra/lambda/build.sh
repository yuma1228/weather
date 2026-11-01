#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../../backend/lambda/ingest/lib/poll_weather_data"

shopt -s nullglob
py_files=( *.py )
if (( ${#py_files[@]} == 0 )); then
  echo "py ファイルがありません" >&2
  exit 1
fi

for src in "${py_files[@]}"; do
  out="${src%.py}.zip"
  python3 -c '
import sys
import zipfile
from pathlib import Path

src = Path(sys.argv[1])
out = Path(sys.argv[2])
with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
    zf.write(src, src.name)
print(out.resolve())
' "$src" "$out"
done
