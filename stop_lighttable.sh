#!/bin/bash
# Stops only the Light table interface. The Postroom (port 8503), its jobs and the Links tool keep running.
# Test switch: LIGHTTABLE_PORT
PORT_LT="${LIGHTTABLE_PORT:-8504}"
pids=$(lsof -tiTCP:"$PORT_LT" -sTCP:LISTEN 2>/dev/null)
if [ -n "$pids" ]; then kill $pids 2>/dev/null && echo "stopped the Light table on port $PORT_LT"; else echo "the Light table was not running"; fi
exit 0
