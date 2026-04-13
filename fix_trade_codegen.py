#!/usr/bin/env python3
"""Fix codegen.py: remove broken trade guard code, insert clean version."""
from pathlib import Path

p = Path("/opt/aetherlang_agents/nous/codegen.py")
lines = p.read_text().splitlines(keepends=True)

# 1. Remove any broken trade guard code (lines with tg_args, TradeGuard init)
clean = []
skip_until_dedent = False
for line in lines:
    if 'tg_args = f"world_name' in line:
        continue
    if "trade_guard = TradeGuard(" in line and "self._emit" in line and "f\"" in line:
        continue
    clean.append(line)

# 2. Find the insertion point: after self._emit("channels = runtime.channels")
result = []
inserted = False
for i, line in enumerate(clean):
    result.append(line)
    if not inserted and 'channels = runtime.channels' in line and 'self._emit' in line:
        # Write the trade guard block using single quotes to avoid escaping hell
        block = [
            '        # Trade guard initialization\n',
            '        trade_laws = self._get_trade_laws()\n',
            '        if any(k in trade_laws for k in ("require_approval", "max_position", "max_daily_loss")):\n',
            '            self._emit("# Initialize trade guard")\n',
            '            self._emit("global trade_guard")\n',
            '            self._emit("from trading import TradeGuard")\n',
            '            wn = self.program.world.name if self.program.world else "default"\n',
            '            ra = trade_laws.get("require_approval", False)\n',
            '            nl = trade_laws.get("no_live_trading", True)\n',
            '            mp = trade_laws.get("max_position", 0)\n',
            '            md = trade_laws.get("max_daily_loss", 0)\n',
            '            at = trade_laws.get("approval_timeout", 120.0)\n',
            '            parts = [\n',
            '                \'world_name="\' + wn + \'"\',\n',
            '                "require_approval=" + str(ra),\n',
            '                "no_live_trading=" + str(nl),\n',
            '                "max_position=" + str(mp),\n',
            '                "max_daily_loss=" + str(md),\n',
            '                "approval_timeout=" + str(at),\n',
            '            ]\n',
            '            self._emit("trade_guard = TradeGuard(" + ", ".join(parts) + ")")\n',
            '            self._emit("await trade_guard.start()")\n',
        ]
        result.extend(block)
        inserted = True

p.write_text("".join(result))
print("Done" if inserted else "ERROR: insertion point not found")
