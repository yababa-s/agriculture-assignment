#!/usr/bin/env bash
# Render a .pptx/.docx to PDF with Keynote/Pages, then each page to PNG: reports/render.sh file outdir [dpi]
set -euo pipefail
IN="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"; mkdir -p "$2"; OUT="$(cd "$2" && pwd)"; DPI="${3:-80}"
PDF="$OUT/$(basename "${1%.*}").pdf"; rm -f "$PDF"
case "$IN" in *.docx) APP="Pages" ;; *) APP="Keynote" ;; esac
osascript <<OSA
with timeout of 300 seconds
tell application "$APP"
  activate
  close every document saving no
  open (POSIX file "$IN")
  set d to missing value
  repeat 30 times
    delay 1
    repeat with x in documents
      if (name of x) contains "$(basename "${1%.*}")" then set d to x
    end repeat
    if d is not missing value then exit repeat
  end repeat
  export d to (POSIX file "$PDF") as PDF
  close every document saving no
end tell
end timeout
OSA
rm -f "$OUT"/slide-*.png
"$(dirname "$0")/../.venv/bin/python" - "$PDF" "$OUT" "$DPI" <<'PY'
import sys, pymupdf
d = pymupdf.open(sys.argv[1])
for i, p in enumerate(d, 1):
    p.get_pixmap(dpi=int(sys.argv[3])).save(f"{sys.argv[2]}/slide-{i:02d}.png")
print(len(d), "pages ->", sys.argv[1])
PY
