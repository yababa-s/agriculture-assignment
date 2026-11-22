#!/usr/bin/env bash
# Convert a .docx (via Pages) or .pptx (via Keynote) to PDF on macOS: reports/to_pdf.sh IN OUT.pdf
set -euo pipefail
IN="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"; OUT="$(cd "$(dirname "$2")" && pwd)/$(basename "$2")"
case "$IN" in
  *.docx) APP="Pages" ;;
  *.pptx) APP="Keynote" ;;
  *) echo "unsupported: $IN"; exit 1 ;;
esac
osascript <<OSA
with timeout of 600 seconds
tell application "$APP"
  set d to open (POSIX file "$IN")
  delay 3
  export d to (POSIX file "$OUT") as PDF
  close d saving no
end tell
end timeout
OSA
echo "$OUT"
