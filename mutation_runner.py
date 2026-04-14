#!/usr/bin/env python3
import asyncio
import logging
import sys
import os
sys.path.insert(0, "/opt/aetherlang_agents/nous")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)s | %(levelname)s | %(message)s',
    datefmt='%H:%M:%S',
)

from pathlib import Path
env_file = Path("/opt/aetherlang_agents/.env")
if env_file.exists():
    for line in env_file.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from mutation_test_gen import build_runtime

async def bad_data_source(**kwargs):
    return "<<<CORRUPTED:{price: not_a_number, timestamp: ???}>>>"

rt = build_runtime()
rt.sense_executor.register_tool("bad_data_source", bad_data_source)

keys = [k for k in ["DEEPSEEK_API_KEY", "MISTRAL_API_KEY", "ANTHROPIC_API_KEY"] if os.environ.get(k)]
print(f"LLM API keys available: {keys}")
print(f"Immune engine: {'ACTIVE' if rt._immune_engine else 'NOT FOUND'}")

asyncio.run(rt.run())
