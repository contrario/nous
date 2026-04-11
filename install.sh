#!/bin/bash
# NOUS CLI wrapper — install to /usr/local/bin/nous
NOUS_DIR="/opt/aetherlang_agents/nous"
exec python3 "$NOUS_DIR/cli.py" "$@"
