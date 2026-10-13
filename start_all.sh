#!/bin/bash
# Starts the Postroom and the model review dashboard (each only if it is not already running), then opens the page.
#   start_all.sh            start both, open the Postroom
#   start_all.sh review     start both, open the model review dashboard instead
# Everything else (the Links tool, the automatic video analysis) is started by the Postroom itself.
# Test switches: POSTROOM_PORT, REVIEW_PORT, NO_OPEN=1

ROOT="/Users/hugodyson/instagram-bot-2"
PORT_POST="${POSTROOM_PORT:-8503}"
PORT_REV="${REVIEW_PORT:-8765}"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export PYTHONUNBUFFERED=1
mkdir -p "$ROOT/logs"
if [ ! -t 1 ]; then exec >> "$ROOT/logs/launcher.log" 2>&1; fi          # started from an app: keep a log
echo "--- $(date) start_all.sh $*"

up() { curl -s -o /dev/null -m 2 "http://127.0.0.1:$1/"; }

if up "$PORT_POST"; then
  echo "Postroom already running"
else
  echo "starting the Postroom..."
  cd "$ROOT" && nohup /usr/bin/python3 server.py --no-open --port "$PORT_POST" >> "$ROOT/logs/postroom.log" 2>&1 &
  disown
fi

if up "$PORT_REV"; then
  echo "Review dashboard already running"
else
  echo "starting the review dashboard..."
  cd "$ROOT/CLIP Training" && REVIEW_PORT="$PORT_REV" nohup .venv/bin/python -u scripts/review_server.py >> "$ROOT/logs/review.log" 2>&1 &
  disown
fi

# wait (up to 90 s) until both answer
for i in $(seq 1 90); do
  if up "$PORT_POST" && up "$PORT_REV"; then break; fi
  sleep 1
done

if up "$PORT_POST" && up "$PORT_REV"; then
  echo "everything is up"
else
  echo "something did not start; see $ROOT/logs/"
  osascript -e 'display notification "A server did not start. See instagram-bot-2/logs." with title "Postroom"' 2>/dev/null
fi

if [ -z "$NO_OPEN" ]; then
  if [ "$1" = "review" ]; then open "http://localhost:$PORT_REV"; else open "http://localhost:$PORT_POST"; fi
fi
