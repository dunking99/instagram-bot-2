#!/bin/bash
# Stops the Postroom, the Links tool inside it, the model review dashboard, and any analysis that is running.
# Test switches: POSTROOM_PORT, REVIEW_PORT, LINKS_PORT
PORT_POST="${POSTROOM_PORT:-8503}"; PORT_REV="${REVIEW_PORT:-8765}"; PORT_LINKS="${LINKS_PORT:-8791}"
for p in "$PORT_POST" "$PORT_REV" "$PORT_LINKS"; do
  pids=$(lsof -tiTCP:"$p" -sTCP:LISTEN 2>/dev/null)
  [ -n "$pids" ] && kill $pids 2>/dev/null && echo "stopped the server on port $p"
done
if [ -z "$POSTROOM_PORT" ]; then pkill -TERM -f "auto_analyse.py --once" 2>/dev/null && echo "stopped the running analysis"; fi
exit 0
