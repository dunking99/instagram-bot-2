#!/bin/bash
# Starts the Light table (and the Postroom behind it, if that is not already running), then opens it.
#   start_lighttable.sh          start and open http://localhost:8504
# The Light table is a second interface for the same Postroom: it shows the same videos, frames, favourites and jobs.
# The ordinary Postroom (http://localhost:8503) is untouched and keeps working on its own.
# Test switches: POSTROOM_PORT, LIGHTTABLE_PORT, NO_OPEN=1

ROOT="/Users/hugodyson/instagram-bot-2"
PORT_POST="${POSTROOM_PORT:-8503}"
PORT_LT="${LIGHTTABLE_PORT:-8504}"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export PYTHONUNBUFFERED=1
mkdir -p "$ROOT/logs"
if [ ! -t 1 ]; then exec >> "$ROOT/logs/lighttable-launcher.log" 2>&1; fi
echo "--- $(date) start_lighttable.sh"

up() { curl -s -o /dev/null -m 2 "http://127.0.0.1:$1/"; }

if up "$PORT_POST"; then
  echo "Postroom already running"
else
  echo "starting the Postroom..."
  cd "$ROOT" && nohup /usr/bin/python3 server.py --no-open --port "$PORT_POST" >> "$ROOT/logs/postroom.log" 2>&1 &
  disown
fi

if up "$PORT_LT"; then
  echo "Light table already running"
else
  if [ ! -f "$ROOT/ui-lighttable/dist/index.html" ]; then
    echo "building the Light table interface (first run)..."
    (cd "$ROOT/ui-lighttable" && npx vite build) >> "$ROOT/logs/lighttable.log" 2>&1
  fi
  echo "starting the Light table..."
  cd "$ROOT" && LIGHTTABLE_PORT="$PORT_LT" POSTROOM_URL="http://127.0.0.1:$PORT_POST" nohup /usr/bin/python3 lighttable_server.py >> "$ROOT/logs/lighttable.log" 2>&1 &
  disown
fi

for i in $(seq 1 90); do
  if up "$PORT_POST" && up "$PORT_LT"; then break; fi
  sleep 1
done

if up "$PORT_POST" && up "$PORT_LT"; then
  echo "everything is up"
else
  echo "something did not start; see $ROOT/logs/"
  osascript -e 'display notification "A server did not start. See instagram-bot-2/logs." with title "Light table"' 2>/dev/null
fi

if [ -z "$NO_OPEN" ]; then open "http://localhost:$PORT_LT"; fi
