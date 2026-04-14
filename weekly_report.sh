#!/bin/bash
cd /opt/aetherlang_agents/nous
REPORT=$(python3 -c "
from pathlib import Path
from noesis_engine import NoesisEngine
e = NoesisEngine()
e.load(Path('noesis_lattice.json'))
try:
    r = e.weekly_report()
    print(r if isinstance(r, str) else str(r))
except Exception as ex:
    atoms = len(e.lattice.atoms)
    print(f'📊 ΝΟΗΣΗ Weekly\nAtoms: {atoms}\n(Report module not available: {ex})')
" 2>/dev/null)

source /opt/aetherlang_agents/.env
curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
  -d "chat_id=${TELEGRAM_CHAT_ID}" \
  -d "text=${REPORT}" > /dev/null
