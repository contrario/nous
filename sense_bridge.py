"""
sense_bridge.py — Connects NOUS SenseExecutor to live AetherLang tools
Noosphere Session 49 | Bridges NOUS runtime ↔ production tool registry

Usage:
    from nous.sense_bridge import register_live_senses
    register_live_senses(nous_runtime)
"""
import logging
from typing import Any

log = logging.getLogger("nous.sense_bridge")


def register_live_senses(nous_runtime) -> int:
    """
    Register real AetherLang tools into NOUS SenseExecutor.
    Returns count of registered senses.
    """
    executor = nous_runtime.sense_executor
    registered = 0

    # ── web_search ──
    try:
        from aetherlang_agents.tools.search_tools import WebSearchTool
        _ws = WebSearchTool()

        async def sense_web_search(**kwargs) -> Any:
            query = kwargs.get("_pos_0") or kwargs.get("query", "")
            result = await _ws.execute(query=query)
            return result.output if hasattr(result, "output") else str(result)

        executor.register_tool("web_search", sense_web_search)
        registered += 1
        log.info("sense_bridge: web_search registered")
    except Exception as e:
        log.warning(f"sense_bridge: web_search failed: {e}")

    # ── memory_recall ──
    try:
        from aetherlang_agents.tools.memory_tools import MemoryRecallTool
        _mr = MemoryRecallTool()

        async def sense_memory_recall(**kwargs) -> Any:
            query = kwargs.get("_pos_0") or kwargs.get("query", "")
            result = await _mr.execute(query=query, **{k: v for k, v in kwargs.items() if k != "_pos_0" and k != "query"})
            return result.output if hasattr(result, "output") else str(result)

        executor.register_tool("memory_recall", sense_memory_recall)
        registered += 1
        log.info("sense_bridge: memory_recall registered")
    except Exception as e:
        log.warning(f"sense_bridge: memory_recall failed: {e}")

    # ── memory_store ──
    try:
        from aetherlang_agents.tools.memory_tools import MemoryStoreTool
        _ms = MemoryStoreTool()

        async def sense_memory_store(**kwargs) -> Any:
            key = kwargs.get("_pos_0") or kwargs.get("key", "")
            value = kwargs.get("_pos_1") or kwargs.get("value", "")
            result = await _ms.execute(key=key, value=value)
            return result.output if hasattr(result, "output") else str(result)

        executor.register_tool("memory_store", sense_memory_store)
        registered += 1
        log.info("sense_bridge: memory_store registered")
    except Exception as e:
        log.warning(f"sense_bridge: memory_store failed: {e}")

    # ── delegate_task ──
    try:
        from aetherlang_agents.tools.delegation_tools import DelegateTaskTool
        _dt = DelegateTaskTool()

        async def sense_delegate_task(**kwargs) -> Any:
            agent = kwargs.get("_pos_0") or kwargs.get("agent_id", "")
            task = kwargs.get("_pos_1") or kwargs.get("task", "")
            result = await _dt.execute(agent_id=agent, task=task)
            return result.output if hasattr(result, "output") else str(result)

        executor.register_tool("delegate_task", sense_delegate_task)
        registered += 1
        log.info("sense_bridge: delegate_task registered")
    except Exception as e:
        log.warning(f"sense_bridge: delegate_task failed: {e}")

    # ── use_skill ──
    try:
        from aetherlang_agents.tools.skill_tool import UseSkillTool
        _sk = UseSkillTool()

        async def sense_use_skill(**kwargs) -> Any:
            skill_id = kwargs.get("_pos_0") or kwargs.get("skill_id", "")
            params = kwargs.get("_pos_1") or kwargs.get("params", {})
            result = await _sk.execute(skill_id=skill_id, params=params)
            return result.output if hasattr(result, "output") else str(result)

        executor.register_tool("use_skill", sense_use_skill)
        registered += 1
        log.info("sense_bridge: use_skill registered")
    except Exception as e:
        log.warning(f"sense_bridge: use_skill failed: {e}")

    log.info(f"sense_bridge: {registered}/5 senses registered")
    return registered
