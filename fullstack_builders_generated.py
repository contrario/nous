"""
NOUS Generated Code — FullStackBuilders
Auto-generated from .nous source. Do not edit manually.
Runtime: Python 3.11+ asyncio | Event-Driven Architecture
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

try:
    from pydantic import BaseModel, Field
except ImportError:
    BaseModel = object
    def Field(**kw): return kw.get('default')

from runtime import (
    NousRuntime, SoulRunner, SoulWakeStrategy,
    CircuitBreakerTripped, CostTracker, SenseCache,
    ChannelRegistry, SenseExecutor, DistributedRuntime,
)

log = logging.getLogger('nous.runtime')

# ═══ World Laws ═══

WORLD_NAME = "FullStackBuilders"
HEARTBEAT_SECONDS = 300
COST_CEILING = 0.5
LAW_COSTCEILING = 0.5
LAW_MAXLATENCY = 90
LAW_ALWAYSRLS = True
LAW_ALWAYSDISCLAIMER = True
LAW_NEVERCOMPETE = True

ENTRYPOINT_SOULS = ['LovableExpert']
LISTENER_SOULS = ['SupabaseExpert']

# ═══ Message Types ═══

class SchemaRequest(BaseModel):
    tables: str
    auth_flow: str
    realtime_needed: bool
    rls_requirements: str
    source: str

class SchemaReady(BaseModel):
    sql: str
    rls_policies: str
    typescript_types: str
    edge_functions: Optional[str]
    integration_notes: str
    source: str

class PromptSequence(BaseModel):
    step_number: int
    prompt_text: str
    mode: str
    depends_on: Optional[int]
    source: str

class SecurityReview(BaseModel):
    target: str
    findings: str
    severity: str
    source: str

class BuildPlan(BaseModel):
    architecture: str
    pages: list[str]
    components: list[str]
    supabase_tables: list[str]
    auth_type: str
    source: str


# ═══ Soul Definitions ═══

class Soul_LovableExpert:
    """Soul: LovableExpert | Wake: HEARTBEAT"""

    def __init__(self, runtime: NousRuntime) -> None:
        self.name = "LovableExpert"
        self._runtime = runtime
        self.model = "claude-haiku"
        self.tier = "Tier0A"
        self.senses = ['web_search', 'memory_recall', 'memory_store', 'delegate_task', 'use_skill']
        self.cycle_count = 0
        self.apps_designed = 0
        self.prompts_generated = 0
        self.last_architecture = ""
        self.knowledge_files_created = 0
        self.dna_temperature = 0.2
        self.dna_max_tokens = 8000
        self.dna_detail_level = 0.85

    async def _sense(self, tool_name: str, **kwargs: Any) -> Any:
        return await self._runtime.sense_executor.call(tool_name, kwargs)

    async def instinct(self) -> None:
        """Instinct cycle for LovableExpert"""
        context = await self._sense("memory_recall", _pos_0="lovable_patterns")
        plan = BuildPlan(architecture="SPA + Supabase", pages=[], components=[], supabase_tables=[], auth_type="email_password", source=self)
        await self._runtime.channels.send("LovableExpert_SchemaRequest", SchemaRequest(tables=plan.supabase_tables, auth_flow=plan.auth_type, realtime_needed=False, rls_requirements="user owns data", source=self))
        schema = await self._runtime.channels.receive("SupabaseExpert_SchemaReady")
        if not ((schema.rls_policies != "")):
            return
        await self._runtime.channels.send("LovableExpert_PromptSequence", PromptSequence(step_number=1, prompt_text="Foundation: layout, routing, auth pages", mode="agent_mode", depends_on=null, source=self))
        self.apps_designed += 1
        await self._sense("memory_store", _pos_0="lovable_architecture", _pos_1=plan.architecture)

    async def heal(self, error: Exception) -> bool:
        error_type = type(error).__name__.lower()
        if error_type == "timeout" or "timeout" in str(error).lower():
            for _retry in range(2):
                await asyncio.sleep(2 ** _retry)
                try:
                    await self.instinct()
                    break
                except Exception:
                    continue
            return True
        elif error_type == "api_error" or "api_error" in str(error).lower():
            await asyncio.sleep(HEARTBEAT_SECONDS * 2)
            for _retry in range(1):
                await asyncio.sleep(1)
                try:
                    await self.instinct()
                    break
                except Exception:
                    continue
            return True
        elif error_type == "hallucination" or "hallucination" in str(error).lower():
            self.dna_temperature = max(0, self.dna_temperature - 0.1)
            log.info(f'{self.name}: lowered temperature to {self.dna_temperature}')
            for _retry in range(1):
                await asyncio.sleep(1)
                try:
                    await self.instinct()
                    break
                except Exception:
                    continue
            return True
        log.warning(f'{self.name}: unhandled error: {error}')
        return False

class Soul_SupabaseExpert:
    """Soul: SupabaseExpert | Wake: LISTENER"""

    def __init__(self, runtime: NousRuntime) -> None:
        self.name = "SupabaseExpert"
        self._runtime = runtime
        self.model = "claude-haiku"
        self.tier = "Tier0A"
        self.senses = ['web_search', 'memory_recall', 'memory_store', 'delegate_task', 'use_skill']
        self.cycle_count = 0
        self.schemas_designed = 0
        self.rls_policies_written = 0
        self.last_schema = ""
        self.edge_functions_created = 0
        self.dna_temperature = 0.15
        self.dna_max_tokens = 8000
        self.dna_security_strictness = 0.95

    async def _sense(self, tool_name: str, **kwargs: Any) -> Any:
        return await self._runtime.sense_executor.call(tool_name, kwargs)

    async def instinct(self) -> None:
        """Instinct cycle for SupabaseExpert"""
        request = await self._runtime.channels.receive("LovableExpert_SchemaRequest")
        schema_sql = "CREATE TABLE..."
        rls = "CREATE POLICY..."
        if not ((rls != "")):
            return
        types = "interface Profile { id: string; ... }"
        edge_fn = ("handle_new_user trigger" if (request.auth_flow != "none") else null)
        await self._runtime.channels.send("SupabaseExpert_SchemaReady", SchemaReady(sql=schema_sql, rls_policies=rls, typescript_types=types, edge_functions=edge_fn, integration_notes="Sync types in Lovable after migration", source=self))
        self.schemas_designed += 1
        self.rls_policies_written += 1
        await self._sense("memory_store", _pos_0="supabase_schema", _pos_1=schema_sql)

    async def heal(self, error: Exception) -> bool:
        error_type = type(error).__name__.lower()
        if error_type == "timeout" or "timeout" in str(error).lower():
            for _retry in range(3):
                await asyncio.sleep(2 ** _retry)
                try:
                    await self.instinct()
                    break
                except Exception:
                    continue
            return True
        elif error_type == "api_error" or "api_error" in str(error).lower():
            await asyncio.sleep(HEARTBEAT_SECONDS * 1)
            for _retry in range(1):
                await asyncio.sleep(1)
                try:
                    await self.instinct()
                    break
                except Exception:
                    continue
            return True
        elif error_type == "budget_exceeded" or "budget_exceeded" in str(error).lower():
            log.info(f'{self.name}: hibernating until next cycle')
            await asyncio.sleep(HEARTBEAT_SECONDS)
            return True
        log.warning(f'{self.name}: unhandled error: {error}')
        return False

# ═══ Runtime Builder ═══

def build_runtime() -> NousRuntime:
    """Build event-driven runtime for FullStackBuilders"""
    rt = NousRuntime(
        world_name="FullStackBuilders",
        heartbeat_seconds=HEARTBEAT_SECONDS,
        cost_ceiling=COST_CEILING,
    )

    _soul_lovableexpert = Soul_LovableExpert(rt)
    rt.add_soul(SoulRunner(
        name="LovableExpert",
        wake_strategy=SoulWakeStrategy.HEARTBEAT,
        instinct_fn=_soul_lovableexpert.instinct,
        heal_fn=_soul_lovableexpert.heal,
        listen_channel=None,
        heartbeat_seconds=HEARTBEAT_SECONDS,
        tier="Tier0A",
    ))

    _soul_supabaseexpert = Soul_SupabaseExpert(rt)
    rt.add_soul(SoulRunner(
        name="SupabaseExpert",
        wake_strategy=SoulWakeStrategy.LISTENER,
        instinct_fn=_soul_supabaseexpert.instinct,
        heal_fn=_soul_supabaseexpert.heal,
        listen_channel="LovableExpert_SchemaRequest",
        heartbeat_seconds=HEARTBEAT_SECONDS,
        tier="Tier0A",
    ))

    return rt


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(name)s | %(levelname)s | %(message)s',
        datefmt='%H:%M:%S',
    )
    rt = build_runtime()
    asyncio.run(rt.run())