#!/bin/bash
# Stops Video Finder.
kill $(lsof -ti tcp:${FINDER_PORT:-8792}) 2>/dev/null && echo stopped || echo "not running"
