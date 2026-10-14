#!/bin/zsh
# Needs a Python with modern OpenSSL: the macOS one (/usr/bin/python3, LibreSSL 2.8) cannot reach porntrex's CDN (TLS alert).
cd "$(dirname "$0")"
kill $(lsof -ti tcp:8793) 2>/dev/null; sleep 0.5
nohup /opt/homebrew/bin/python3 server.py >> server.log 2>&1 &
echo "Stream test on http://127.0.0.1:8793"
