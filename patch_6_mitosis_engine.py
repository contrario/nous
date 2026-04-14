path = "/opt/aetherlang_agents/nous/mitosis_engine.py"
with open(path, "r") as f:
    content = f.read()

old_config = '''@dataclass
class MitosisConfig:
    trigger_fn: Callable[[dict[str, Any]], bool]
    trigger_expr: str = ""
    max_clones: int = 3
    cooldown_seconds: float = 60.0
    clone_tier: Optional[str] = None
    verify: bool = True'''

new_config = '''@dataclass
class MitosisConfig:
    trigger_fn: Callable[[dict[str, Any]], bool]
    trigger_expr: str = ""
    max_clones: int = 3
    cooldown_seconds: float = 60.0
    clone_tier: Optional[str] = None
    verify: bool = True
    retire_trigger_fn: Optional[Callable[[dict[str, Any]], bool]] = None
    retire_cooldown_seconds: float = 120.0
    min_clones: int = 0'''

if old_config in content:
    content = content.replace(old_config, new_config)

old_clone_record = '''@dataclass
class CloneRecord:
    parent_name: str
    clone_name: str
    clone_index: int
    created_at: float
    tier: str
    verified: bool
    verification_result: Optional[str] = None'''

new_clone_record = '''@dataclass
class CloneRecord:
    parent_name: str
    clone_name: str
    clone_index: int
    created_at: float
    tier: str
    verified: bool
    verification_result: Optional[str] = None
    retired_at: Optional[float] = None
    retirement_reason: Optional[str] = None'''

if old_clone_record in content:
    content = content.replace(old_clone_record, new_clone_record)

old_init_tail = '''        self._total_clones = 0
        self._total_verified = 0
        self._total_rejected = 0'''

new_init_tail = '''        self._total_clones = 0
        self._total_verified = 0
        self._total_rejected = 0
        self._total_retired = 0
        self._last_retirement: dict[str, float] = {}
        self._retired_records: list[CloneRecord] = []'''

if old_init_tail in content:
    content = content.replace(old_init_tail, new_init_tail)

old_check_all = '''    async def _check_all(self) -> None:
        for soul_name, config in self._configs.items():
            try:
                await self._check_soul(soul_name, config)
            except Exception as e:
                log.error(f"Mitosis check failed for {soul_name}: {e}")'''

new_check_all = '''    async def _check_all(self) -> None:
        for soul_name, config in self._configs.items():
            try:
                await self._check_soul(soul_name, config)
            except Exception as e:
                log.error(f"Mitosis check failed for {soul_name}: {e}")
            try:
                await self._check_retirement(soul_name, config)
            except Exception as e:
                log.error(f"Retirement check failed for {soul_name}: {e}")

    async def _check_retirement(self, soul_name: str, config: MitosisConfig) -> None:
        if config.retire_trigger_fn is None:
            return

        active_clones = self._clones.get(soul_name, [])
        if len(active_clones) <= config.min_clones:
            return

        now = time.time()
        last = self._last_retirement.get(soul_name, 0.0)
        if (now - last) < config.retire_cooldown_seconds:
            return

        metrics = self._metrics.get(soul_name)
        if not metrics:
            return

        eval_dict = metrics.to_eval_dict()
        try:
            should_retire = config.retire_trigger_fn(eval_dict)
        except Exception as e:
            log.warning(f"Retirement trigger eval failed for {soul_name}: {e}")
            return

        if not should_retire:
            return

        clone_to_retire = active_clones[-1]

        log.info(
            f"═══ RETIREMENT TRIGGERED: {soul_name} ═══\\n"
            f"  Retiring: {clone_to_retire.clone_name}\\n"
            f"  Metrics: cycles={metrics.cycle_count}, "
            f"latency={metrics.last_latency_ms:.0f}ms, "
            f"queue={metrics.queue_depth}\\n"
            f"  Reason: retire_trigger condition met"
        )

        await self._retire_clone(soul_name, clone_to_retire)
        self._last_retirement[soul_name] = now

    async def _retire_clone(self, parent_name: str, record: CloneRecord) -> None:
        runner = self._find_runner(record.clone_name)
        if runner:
            runner.stop()
            await asyncio.sleep(0.1)
            self._runtime.remove_soul(record.clone_name)
            log.info(f"  Clone runner stopped: {record.clone_name}")

        record.retired_at = time.time()
        record.retirement_reason = "retire_trigger"
        self._retired_records.append(record)

        if parent_name in self._clones:
            self._clones[parent_name] = [
                c for c in self._clones[parent_name]
                if c.clone_name != record.clone_name
            ]

        self._total_retired += 1
        remaining = len(self._clones.get(parent_name, []))
        config = self._configs.get(parent_name)
        max_c = config.max_clones if config else "?"

        log.info(
            f"  Clone RETIRED: {record.clone_name}\\n"
            f"  Lifetime: {record.retired_at - record.created_at:.1f}s\\n"
            f"  Active clones of {parent_name}: {remaining}/{max_c}\\n"
            f"  Total retired: {self._total_retired}\\n"
            f"  ═══ RETIREMENT COMPLETE ═══"
        )'''

if old_check_all in content:
    content = content.replace(old_check_all, new_check_all)

old_status_result = '''        result: dict[str, Any] = {
            "total_clones": self._total_clones,
            "total_verified": self._total_verified,
            "total_rejected": self._total_rejected,
            "souls": {},
        }'''

new_status_result = '''        result: dict[str, Any] = {
            "total_clones": self._total_clones,
            "total_verified": self._total_verified,
            "total_rejected": self._total_rejected,
            "total_retired": self._total_retired,
            "souls": {},
        }'''

if old_status_result in content:
    content = content.replace(old_status_result, new_status_result)

old_print_totals = '''        lines.append(f"  Total clones spawned:  {self._total_clones}")
        lines.append(f"  Verified:              {self._total_verified}")
        lines.append(f"  Rejected:              {self._total_rejected}")'''

new_print_totals = '''        lines.append(f"  Total clones spawned:  {self._total_clones}")
        lines.append(f"  Verified:              {self._total_verified}")
        lines.append(f"  Rejected:              {self._total_rejected}")
        lines.append(f"  Retired:               {self._total_retired}")'''

if old_print_totals in content:
    content = content.replace(old_print_totals, new_print_totals)

old_soul_status = '''            lines.append(f"  Active clones: {len(clones)}/{config.max_clones}")
            for c in clones:
                v_icon = "✓" if c.verified else "○"
                lines.append(f"    {v_icon} {c.clone_name} @ {c.tier}")
            lines.append("")'''

new_soul_status = '''            lines.append(f"  Min clones:    {config.min_clones}")
            has_retire = config.retire_trigger_fn is not None
            lines.append(f"  Retirement:    {'enabled' if has_retire else 'disabled'}")
            if has_retire:
                lines.append(f"  Retire CD:     {config.retire_cooldown_seconds}s")
            lines.append(f"  Active clones: {len(clones)}/{config.max_clones}")
            for c in clones:
                v_icon = "✓" if c.verified else "○"
                age = time.time() - c.created_at
                lines.append(f"    {v_icon} {c.clone_name} @ {c.tier} (age {age:.0f}s)")
            if self._retired_records:
                parent_retired = [r for r in self._retired_records if r.parent_name == soul_name]
                if parent_retired:
                    lines.append(f"  Retired clones: {len(parent_retired)}")
                    for r in parent_retired[-3:]:
                        lifetime = (r.retired_at or 0) - r.created_at
                        lines.append(f"    ✗ {r.clone_name} (lived {lifetime:.0f}s)")
            lines.append("")'''

if old_soul_status in content:
    content = content.replace(old_soul_status, new_soul_status)

with open(path, "w") as f:
    f.write(content)
print("PATCH 6 OK — mitosis_engine updated with retirement")
