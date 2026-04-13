#!/usr/bin/env python3
"""Patch codegen.py and validator.py for TradeGuard integration."""
from pathlib import Path

BASE = Path("/opt/aetherlang_agents/nous")


def patch_codegen() -> None:
    p = BASE / "codegen.py"
    c = p.read_text()

    if "TradeGuard" in c:
        print("[SKIP] codegen.py already has TradeGuard")
        return

    # 1. Add import
    c = c.replace(
        "from ast_nodes import (",
        "from ast_nodes import (\n    # TradeGuard imported at runtime in generated code",
    )

    # 2. Add helper method to detect trade laws
    trade_helper = '''
    def _get_trade_laws(self) -> dict[str, Any]:
        """Extract trading-related laws."""
        laws: dict[str, Any] = {}
        if not self.program.world:
            return laws
        for law in self.program.world.laws:
            name_lower = law.name.lower()
            if name_lower == "nolivetrading":
                laws["no_live_trading"] = getattr(law.expr, "value", True)
            elif name_lower == "requireapproval":
                laws["require_approval"] = getattr(law.expr, "value", False)
            elif name_lower == "maxpositionsize":
                laws["max_position"] = getattr(law.expr, "amount", 0)
            elif name_lower == "maxdailyloss":
                laws["max_daily_loss"] = getattr(law.expr, "amount", 0)
            elif name_lower == "approvaltimeout":
                laws["approval_timeout"] = getattr(law.expr, "value", 120)
        return laws

'''

    # Insert before _emit_soul_classes
    marker = "    def _emit_soul_classes"
    if marker in c:
        c = c.replace(marker, trade_helper + "    def _emit_soul_classes")
        print("[OK]   _get_trade_laws helper added")

    # 3. Add TradeGuard initialization in run_world generation
    # Find where run_world is generated and add trade guard setup
    # We need to find the emit for run_world and add trade guard init
    old_run_world_marker = 'self._emit("async def run_world():")'
    if old_run_world_marker in c:
        trade_init = '''
        # Trade guard
        trade_laws = self._get_trade_laws()
        if any(k in trade_laws for k in ("require_approval", "max_position", "max_daily_loss")):
            world_name = self.program.world.name if self.program.world else "default"
            self._emit("    from trading import TradeGuard")
            self._emit(f"    global trade_guard")
            self._emit(f"    trade_guard = TradeGuard(")
            self._emit(f"        world_name=\\"{world_name}\\",")
            self._emit(f"        require_approval={trade_laws.get('require_approval', False)},")
            self._emit(f"        no_live_trading={trade_laws.get('no_live_trading', True)},")
            self._emit(f"        max_position={trade_laws.get('max_position', 0)},")
            self._emit(f"        max_daily_loss={trade_laws.get('max_daily_loss', 0)},")
            self._emit(f"        approval_timeout={trade_laws.get('approval_timeout', 120.0)},")
            self._emit(f"    )")
            self._emit("    await trade_guard.start()")
'''
        # Find the line after run_world declaration to insert trade guard
        idx = c.index(old_run_world_marker)
        # Find next self._emit after that
        next_emit = c.index('self._emit(', idx + len(old_run_world_marker))
        c = c[:next_emit] + trade_init.lstrip('\n') + "        " + c[next_emit:]
        print("[OK]   TradeGuard init in run_world")

    # 4. Add trade_guard global
    if "trade_guard = None" not in c:
        c = c.replace(
            "cross_bus = None",
            "cross_bus = None\ntrade_guard = None  # Set by run_world() if trading laws exist",
        )
        print("[OK]   trade_guard global added")

    p.write_text(c)
    print("[OK]   codegen.py patched")


def patch_validator() -> None:
    p = BASE / "validator.py"
    c = p.read_text()

    if "RequireApproval" in c:
        print("[SKIP] validator.py already has RequireApproval")
        return

    # Add RequireApproval validation after existing C004
    old = "        return result"
    new = '''        # C005: RequireApproval recommended for live trading
        no_live = self._get_bool_law("NoLiveTrading")
        require_approval = self._get_bool_law("RequireApproval")
        if not no_live and not require_approval and has_trading_souls:
            result.warnings.append(
                "[WARN] C005 @ world: Live trading enabled without RequireApproval. "
                "Add: law RequireApproval = true"
            )

        return result'''

    if old in c and "has_trading_souls" in c:
        c = c.replace(old, new, 1)
        print("[OK]   C005 RequireApproval warning added")
    else:
        print("[SKIP] validator.py — insertion point not found")

    p.write_text(c)


def main() -> None:
    print("=== Trading Guard Integration ===")
    patch_codegen()
    patch_validator()

    print("\n=== Test ===")
    print("Add to gate_alpha.nous:")
    print("    law RequireApproval = true")
    print("    law MaxPositionSize = $500")
    print("    law MaxDailyLoss = $100")
    print("\nThen: nous compile gate_alpha.nous")
    print("\nTelegram commands:")
    print("    /stop    — halt all trades")
    print("    /status  — check if active")
    print("    /resume  — resume trading")
    print("    /yes     — approve trade")
    print("    /no      — reject trade")


if __name__ == "__main__":
    main()
