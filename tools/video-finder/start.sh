#!/bin/bash
# Starts Video Finder (if it is not already running) and opens it:  http://127.0.0.1:8792
cd "$(dirname "$0")"
PORT="${FINDER_PORT:-8792}"
if ! curl -s -o /dev/null -m 2 "http://127.0.0.1:$PORT/"; then
  mkdir -p logs
  nohup /usr/bin/python3 -u server.py >> logs/server.log 2>&1 &
  for _ in $(seq 1 20); do sleep 0.3; curl -s -o /dev/null -m 1 "http://127.0.0.1:$PORT/" && break; done
fi
[ -z "$NO_OPEN" ] && open "http://127.0.0.1:$PORT"
echo "Video Finder: http://127.0.0.1:$PORT"
