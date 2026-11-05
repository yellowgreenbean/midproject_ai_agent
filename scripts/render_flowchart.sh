#!/bin/sh
# docs/흐름도.html → docs/흐름도.png (Chrome 헤드리스로 페이지 전체를 찍는다)
set -e
cd "$(dirname "$0")/.."
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
SRC="file://$PWD/docs/흐름도.html"
# 페이지 높이는 HTML 끝의 스크립트가 body data-h 에 적어 둔다
DOM=$("$CHROME" --headless=new --disable-gpu --window-size=1500,2000 --dump-dom "$SRC" 2>/dev/null)
H=$(printf '%s' "$DOM" | sed -n 's/.*data-h="\([0-9]*\)".*/\1/p' | head -1)
OVER=$(printf '%s' "$DOM" | sed -n 's/.*data-over="\([0-9]*\)".*/\1/p' | head -1)
[ -n "$H" ] || { echo "페이지 높이를 못 읽음" >&2; exit 1; }
[ "$OVER" = "0" ] || echo "경고: 테두리 밖으로 삐져나온 칸 ${OVER}개: $(printf '%s' "$DOM" | sed -n 's/.*data-over-list="\([^"]*\)".*/\1/p' | head -1)" >&2
"$CHROME" --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=2 \
  --window-size=1500,"$H" --screenshot="$PWD/docs/흐름도.png" "$SRC" 2>/dev/null
echo "docs/흐름도.png (1500x$H, 2배 해상도)"
