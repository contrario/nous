"""
Noesis Serper Search — Phase 7
===============================
Uses Serper.dev API for Google Search results.
Feeds search results into the Noesis lattice as knowledge atoms.

Env var: SERPER_API_KEY
Usage:
  - Standalone: python3 noesis_serper.py "query" [--lattice path]
  - From code: SerperSource(engine).search_and_learn("query")
  - From Telegram: /search query (after patch)
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx

logger = logging.getLogger("noesis.serper")

SERPER_API_URL = "https://google.serper.dev/search"


@dataclass
class SearchResult:
    title: str
    snippet: str
    link: str
    position: int


@dataclass
class SerperSearchResult:
    query: str
    results: list[SearchResult] = field(default_factory=list)
    answer_box: Optional[str] = None
    knowledge_graph: Optional[dict[str, str]] = None
    duration_s: float = 0.0


class SerperSource:

    def __init__(
        self,
        engine: Optional[object] = None,
        api_key: Optional[str] = None,
        max_results: int = 10,
        timeout: float = 15.0,
    ) -> None:
        self.engine = engine
        self.api_key = api_key or os.getenv("SERPER_API_KEY", "")
        self.max_results = max_results
        self.timeout = timeout
        self.calls: int = 0
        self.total_results: int = 0

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def search(self, query: str, num: int = 0) -> Optional[SerperSearchResult]:
        if not self.available:
            logger.debug("Serper: no API key")
            return None

        num = num or self.max_results
        t0 = time.time()
        self.calls += 1

        payload = {
            "q": query,
            "num": num,
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(
                    SERPER_API_URL,
                    json=payload,
                    headers={
                        "X-API-KEY": self.api_key,
                        "Content-Type": "application/json",
                    },
                )

            if resp.status_code != 200:
                logger.warning(f"Serper API error {resp.status_code}: {resp.text[:200]}")
                return None

            data = resp.json()
            duration = time.time() - t0

            results: list[SearchResult] = []
            for i, item in enumerate(data.get("organic", [])[:num]):
                results.append(SearchResult(
                    title=item.get("title", ""),
                    snippet=item.get("snippet", ""),
                    link=item.get("link", ""),
                    position=i + 1,
                ))

            answer_box = None
            ab = data.get("answerBox")
            if ab:
                answer_box = ab.get("answer") or ab.get("snippet") or ab.get("title")

            kg = None
            kg_data = data.get("knowledgeGraph")
            if kg_data:
                kg = {}
                for k in ("title", "type", "description"):
                    if kg_data.get(k):
                        kg[k] = kg_data[k]
                attrs = kg_data.get("attributes", {})
                if attrs:
                    kg.update(attrs)

            self.total_results += len(results)

            return SerperSearchResult(
                query=query,
                results=results,
                answer_box=answer_box,
                knowledge_graph=kg,
                duration_s=duration,
            )

        except httpx.TimeoutException:
            logger.warning(f"Serper timeout after {self.timeout}s")
            return None
        except Exception as e:
            logger.error(f"Serper error: {e}")
            return None

    def search_and_learn(
        self,
        query: str,
        num: int = 5,
    ) -> dict[str, object]:
        if self.engine is None:
            return {"error": "No engine attached"}

        sr = self.search(query, num=num)
        if sr is None:
            return {"error": "Search failed"}

        atoms_before = len(self.engine.lattice.atoms) if hasattr(self.engine, "lattice") else 0
        learned: list[str] = []

        if sr.answer_box:
            text = f"{query}: {sr.answer_box}"
            try:
                self.engine.learn(text, source=f"serper:answer_box")
                learned.append(text[:80])
            except Exception as e:
                logger.warning(f"Learn error (answer_box): {e}")

        if sr.knowledge_graph:
            kg = sr.knowledge_graph
            title = kg.get("title", query)
            desc = kg.get("description", "")
            if desc:
                text = f"{title}: {desc}"
                try:
                    self.engine.learn(text, source=f"serper:knowledge_graph")
                    learned.append(text[:80])
                except Exception as e:
                    logger.warning(f"Learn error (kg): {e}")

            for k, v in kg.items():
                if k in ("title", "type", "description"):
                    continue
                text = f"{title} {k}: {v}"
                try:
                    self.engine.learn(text, source=f"serper:knowledge_graph")
                    learned.append(text[:80])
                except Exception as e:
                    logger.warning(f"Learn error (kg attr): {e}")

        for r in sr.results:
            if r.snippet and len(r.snippet) > 30:
                text = f"{r.title}. {r.snippet}"
                try:
                    self.engine.learn(text, source=f"serper:{r.link[:60]}")
                    learned.append(text[:80])
                except Exception as e:
                    logger.warning(f"Learn error (result): {e}")

        atoms_after = len(self.engine.lattice.atoms) if hasattr(self.engine, "lattice") else 0

        return {
            "query": query,
            "results_found": len(sr.results),
            "has_answer_box": sr.answer_box is not None,
            "has_knowledge_graph": sr.knowledge_graph is not None,
            "atoms_created": atoms_after - atoms_before,
            "learned_count": len(learned),
            "duration_s": round(sr.duration_s, 3),
        }

    def format_results(self, sr: SerperSearchResult) -> str:
        parts: list[str] = []
        parts.append(f"🔍 Search: {sr.query}")
        parts.append("")

        if sr.answer_box:
            parts.append(f"📋 Answer: {sr.answer_box}")
            parts.append("")

        if sr.knowledge_graph:
            kg = sr.knowledge_graph
            title = kg.get("title", "")
            desc = kg.get("description", "")
            if title:
                parts.append(f"📚 {title}")
            if desc:
                parts.append(f"   {desc}")
            for k, v in kg.items():
                if k in ("title", "type", "description"):
                    continue
                parts.append(f"   {k}: {v}")
            parts.append("")

        for r in sr.results[:5]:
            parts.append(f"{r.position}. {r.title}")
            if r.snippet:
                parts.append(f"   {r.snippet[:150]}")
            parts.append(f"   🔗 {r.link}")
            parts.append("")

        parts.append(f"⏱ {sr.duration_s:.2f}s | {len(sr.results)} results")
        return "\n".join(parts)

    def stats(self) -> dict[str, object]:
        return {
            "provider": "serper",
            "available": self.available,
            "calls": self.calls,
            "total_results": self.total_results,
        }


def main() -> None:
    import argparse
    import sys
    from pathlib import Path

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="Noesis Serper Search")
    parser.add_argument("query", help="Search query")
    parser.add_argument("--lattice", default="noesis_lattice.json", help="Lattice file path")
    parser.add_argument("--num", type=int, default=5, help="Number of results")
    parser.add_argument("--learn", action="store_true", help="Learn results into lattice")
    args = parser.parse_args()

    if args.learn:
        sys.path.insert(0, str(Path(__file__).parent))
        from noesis_engine import NoesisEngine

        engine = NoesisEngine()
        lattice_path = Path(args.lattice)
        if lattice_path.exists():
            engine.load(lattice_path)
            logger.info(f"Loaded lattice: {len(engine.lattice.atoms)} atoms")

        source = SerperSource(engine=engine)
        result = source.search_and_learn(args.query, num=args.num)
        engine.save(lattice_path)

        print(f"\n{'='*60}")
        print(f"Serper Search + Learn")
        print(f"{'='*60}")
        for k, v in result.items():
            print(f"  {k}: {v}")
    else:
        source = SerperSource()
        sr = source.search(args.query, num=args.num)
        if sr is None:
            print("Search failed. Check SERPER_API_KEY.")
            sys.exit(1)
        print(source.format_results(sr))


if __name__ == "__main__":
    main()
