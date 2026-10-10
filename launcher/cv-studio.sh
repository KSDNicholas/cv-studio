#!/bin/bash
# CV Studio launcher: start the local server if it is not running, then open the page.
# Installed as "CV Studio.app/Contents/MacOS/cv-studio" by launcher/build.sh, which fills in REPO.
REPO="__REPO__"
URL="http://127.0.0.1:8765/"
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

alert() { osascript -e "display alert \"CV Studio\" message \"$1\" as critical" >/dev/null 2>&1; }

if curl -s -o /dev/null --max-time 1 "$URL"; then open "$URL"; exit 0; fi
[ -x "$REPO/.venv/bin/python" ] || { alert "Cannot find the repo folder or its .venv at $REPO."; exit 1; }

cd "$REPO" || exit 1
# Script-based apps can start under Rosetta, so run Python natively on Apple Silicon (falls back on Intel Macs).
ARCH=()
[ "$(sysctl -n hw.optional.arm64 2>/dev/null)" = "1" ] && ARCH=(/usr/bin/arch -arm64)
nohup "${ARCH[@]}" "$REPO/.venv/bin/python" -u "$REPO/tools/ui.py" --no-browser >> "$REPO/tools/ui.log" 2>&1 < /dev/null &
disown

for _ in $(seq 1 160); do  # up to about 40 s
  if curl -s -o /dev/null --max-time 1 "$URL"; then open "$URL"; exit 0; fi
  /bin/sleep 0.25
done
alert "The server did not start. See tools/ui.log in the repo folder."
exit 1
