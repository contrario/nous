"""
Νόηση Ingest — Πηγές Γνώσης (Knowledge Sources)
==================================================
Three knowledge sources:
    1. Files  — scan directories for text, markdown, txt, json
    2. APIs   — NASA, Arxiv, Wikipedia, custom endpoints
    3. RSS    — daily feed ingestion via cron

Usage:
    python3 noesis_ingest.py --scan /path/to/dir          # Scan files
    python3 noesis_ingest.py --scan /path --recursive      # Recursive scan
    python3 noesis_ingest.py --nasa                        # NASA APOD
    python3 noesis_ingest.py --nasa-search "black holes"   # NASA search
    python3 noesis_ingest.py --arxiv "quantum computing"   # Arxiv papers
    python3 noesis_ingest.py --wiki "Maillard reaction"    # Wikipedia
    python3 noesis_ingest.py --rss https://feed.url/rss    # Single RSS feed
    python3 noesis_ingest.py --feeds                       # All configured feeds
    python3 noesis_ingest.py --api URL                     # Custom JSON API
    python3 noesis_ingest.py --all                         # Everything

Cron (daily at 4AM):
    0 4 * * * cd /opt/aetherlang_agents/nous && python3 noesis_ingest.py --feeds --nasa >> /var/log/noesis_ingest.log 2>&1

Author: Hlias Staurou + Claude | NOUS Project | April 2026
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Optional

import httpx

from noesis_engine import NoesisEngine

log = logging.getLogger("nous.ingest")

LATTICE_PATH = Path("/opt/aetherlang_agents/nous/noesis_lattice.json")

_ENV_PATH = Path("/opt/aetherlang_agents/.env")
if _ENV_PATH.exists():
    for _line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            _k, _v = _k.strip(), _v.strip().strip("'").strip('"')
            if _k and _v and _k not in os.environ:
                os.environ[_k] = _v

TEXT_EXTENSIONS: set[str] = {".txt", ".md", ".rst", ".csv", ".nous", ".json", ".toml", ".yaml", ".yml"}
MAX_FILE_SIZE: int = 500_000
HTTP_TIMEOUT: float = 20.0

RSS_FEEDS: dict[str, str] = {
    "BBC Science": "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml",
    "NASA Breaking": "https://www.nasa.gov/rss/dyn/breaking_news.rss",
    "Arxiv CS.AI": "http://rss.arxiv.org/rss/cs.AI",
    "Arxiv CS.CL": "http://rss.arxiv.org/rss/cs.CL",
    "TechCrunch AI": "https://techcrunch.com/category/artificial-intelligence/feed/",
    "Hacker News Best": "https://hnrss.org/best",
    "Reuters Tech": "https://www.reutersagency.com/feed/?best-topics=tech",
}


def _http_get(url: str, headers: dict[str, str] | None = None, params: dict[str, str] | None = None) -> Optional[httpx.Response]:
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
            resp = client.get(url, headers=headers or {}, params=params or {})
            resp.raise_for_status()
            return resp
    except Exception as e:
        log.warning(f"HTTP GET failed: {url} — {e}")
        return None


def _strip_html(text: str) -> str:
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'&[a-zA-Z]+;', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


class FileScanner:
    def __init__(self, engine: NoesisEngine) -> None:
        self.engine = engine

    def scan(self, directory: Path, recursive: bool = False) -> tuple[int, int]:
        if not directory.exists():
            print(f"  Directory not found: {directory}")
            return 0, 0
        total_files = 0
        total_atoms = 0
        pattern = "**/*" if recursive else "*"
        for path in sorted(directory.glob(pattern)):
            if not path.is_file():
                continue
            if path.suffix.lower() not in TEXT_EXTENSIONS:
                continue
            if path.stat().st_size > MAX_FILE_SIZE:
                continue
            if any(part.startswith(".") for part in path.parts):
                continue
            if "__pycache__" in str(path):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            if len(text.strip()) < 50:
                continue
            added = self.engine.learn(text, source=f"file:{path.name}")
            if added > 0:
                total_files += 1
                total_atoms += added
                print(f"  +{added:4d} atoms | {path.name}")
        return total_files, total_atoms


class NasaSource:
    BASE_URL = "https://api.nasa.gov"

    def __init__(self, engine: NoesisEngine, api_key: str = "DEMO_KEY") -> None:
        self.engine = engine
        self.api_key = api_key

    def apod(self, count: int = 5) -> int:
        resp = _http_get(
            f"{self.BASE_URL}/planetary/apod",
            params={"api_key": self.api_key, "count": str(count)},
        )
        if resp is None:
            return 0
        total = 0
        for item in resp.json():
            title = item.get("title", "")
            explanation = item.get("explanation", "")
            date = item.get("date", "")
            if explanation:
                text = f"{title}. {explanation}"
                added = self.engine.learn(text, source=f"nasa:apod:{date}")
                total += added
                if added > 0:
                    print(f"  +{added:4d} atoms | NASA APOD: {title[:60]}")
        return total

    def search(self, query: str, max_results: int = 5) -> int:
        resp = _http_get(
            "https://images-api.nasa.gov/search",
            params={"q": query, "media_type": "image"},
        )
        if resp is None:
            return 0
        total = 0
        items = resp.json().get("collection", {}).get("items", [])[:max_results]
        for item in items:
            data = item.get("data", [{}])[0]
            title = data.get("title", "")
            description = data.get("description", "")
            if description and len(description) > 50:
                text = f"{title}. {_strip_html(description)}"
                added = self.engine.learn(text, source=f"nasa:search:{query}")
                total += added
                if added > 0:
                    print(f"  +{added:4d} atoms | NASA: {title[:60]}")
        return total


class ArxivSource:
    BASE_URL = "http://export.arxiv.org/api/query"

    def __init__(self, engine: NoesisEngine) -> None:
        self.engine = engine

    def search(self, query: str, max_results: int = 5) -> int:
        resp = _http_get(
            self.BASE_URL,
            params={
                "search_query": f"all:{query}",
                "start": "0",
                "max_results": str(max_results),
                "sortBy": "relevance",
            },
        )
        if resp is None:
            return 0
        total = 0
        try:
            root = ET.fromstring(resp.text)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            for entry in root.findall("atom:entry", ns):
                title_el = entry.find("atom:title", ns)
                summary_el = entry.find("atom:summary", ns)
                title = title_el.text.strip() if title_el is not None and title_el.text else ""
                summary = summary_el.text.strip() if summary_el is not None and summary_el.text else ""
                if summary and len(summary) > 50:
                    text = f"{title}. {summary}"
                    text = re.sub(r'\s+', ' ', text)
                    added = self.engine.learn(text, source=f"arxiv:{query}")
                    total += added
                    if added > 0:
                        print(f"  +{added:4d} atoms | Arxiv: {title[:60]}")
        except ET.ParseError as e:
            log.warning(f"Arxiv XML parse error: {e}")
        return total


class WikipediaSource:
    BASE_URL = "https://en.wikipedia.org/api/rest_v1/page/summary"

    def __init__(self, engine: NoesisEngine) -> None:
        self.engine = engine

    def lookup(self, topic: str) -> int:
        slug = topic.replace(" ", "_")
        resp = _http_get(
            f"{self.BASE_URL}/{slug}",
            headers={
                "Accept": "application/json",
                "User-Agent": "Noesis/1.0 (NOUS Project; Athens, Greece)",
            },
        )
        if resp is None:
            return 0
        data = resp.json()
        extract = data.get("extract", "")
        title = data.get("title", topic)
        if extract and len(extract) > 50:
            added = self.engine.learn(extract, source=f"wikipedia:{title}")
            if added > 0:
                print(f"  +{added:4d} atoms | Wikipedia: {title}")
            return added
        return 0


class RSSSource:
    def __init__(self, engine: NoesisEngine) -> None:
        self.engine = engine

    def fetch_feed(self, url: str, name: str = "", max_items: int = 10) -> int:
        resp = _http_get(url)
        if resp is None:
            return 0
        total = 0
        try:
            root = ET.fromstring(resp.text)
            items = root.findall(".//item")[:max_items]
            if not items:
                items = root.findall(".//{http://www.w3.org/2005/Atom}entry")[:max_items]
            for item in items:
                title = ""
                description = ""
                title_el = item.find("title")
                if title_el is None:
                    title_el = item.find("{http://www.w3.org/2005/Atom}title")
                if title_el is not None and title_el.text:
                    title = title_el.text.strip()
                desc_el = item.find("description")
                if desc_el is None:
                    desc_el = item.find("{http://www.w3.org/2005/Atom}summary")
                if desc_el is not None and desc_el.text:
                    description = _strip_html(desc_el.text.strip())
                if description and len(description) > 50:
                    text = f"{title}. {description}" if title else description
                    source_name = name or url[:40]
                    added = self.engine.learn(text, source=f"rss:{source_name}")
                    total += added
                    if added > 0:
                        print(f"  +{added:4d} atoms | {source_name}: {title[:50]}")
        except ET.ParseError as e:
            log.warning(f"RSS parse error for {url}: {e}")
        return total

    def fetch_all(self, feeds: dict[str, str] | None = None, max_items: int = 5) -> int:
        feeds = feeds or RSS_FEEDS
        total = 0
        for name, url in feeds.items():
            print(f"\n  --- {name} ---")
            added = self.fetch_feed(url, name=name, max_items=max_items)
            total += added
        return total


class NasaADSSource:
    BASE_URL = "https://api.adsabs.harvard.edu/v1/search/query"

    def __init__(self, engine: NoesisEngine) -> None:
        self.engine = engine
        self.api_key = os.environ.get("NASA_ADS_API_KEY", "")

    def search(self, query: str, max_results: int = 5) -> int:
        if not self.api_key:
            print("  NASA ADS: no API key")
            return 0
        resp = _http_get(
            self.BASE_URL,
            headers={"Authorization": f"Bearer {self.api_key}"},
            params={"q": query, "rows": str(max_results), "fl": "title,abstract,year,author"},
        )
        if resp is None:
            return 0
        total = 0
        docs = resp.json().get("response", {}).get("docs", [])
        for doc in docs:
            title = doc.get("title", [""])[0] if isinstance(doc.get("title"), list) else doc.get("title", "")
            abstract = doc.get("abstract", "")
            year = doc.get("year", "")
            if abstract and len(abstract) > 50:
                text = f"{title} ({year}). {abstract}"
                text = re.sub(r'\s+', ' ', text)
                added = self.engine.learn(text, source=f"nasa_ads:{query}")
                total += added
                if added > 0:
                    print(f"  +{added:4d} atoms | NASA ADS: {title[:60]}")
        return total


class BinanceSource:
    def __init__(self, engine: NoesisEngine) -> None:
        self.engine = engine

    def top_coins(self, limit: int = 10) -> int:
        resp = _http_get("https://api.binance.com/api/v3/ticker/24hr")
        if resp is None:
            return 0
        data = resp.json()
        usdt_pairs = [d for d in data if d.get("symbol", "").endswith("USDT")]
        usdt_pairs.sort(key=lambda x: float(x.get("quoteVolume", 0)), reverse=True)
        total = 0
        for pair in usdt_pairs[:limit]:
            symbol = pair["symbol"].replace("USDT", "")
            price = float(pair.get("lastPrice", 0))
            change = float(pair.get("priceChangePercent", 0))
            volume = float(pair.get("quoteVolume", 0))
            direction = "up" if change > 0 else "down"
            text = (
                f"{symbol} is trading at ${price:,.2f}, "
                f"{direction} {abs(change):.1f}% in 24 hours "
                f"with ${volume:,.0f} trading volume."
            )
            added = self.engine.learn(text, source=f"binance:{symbol}")
            total += added
        if total > 0:
            print(f"  +{total:4d} atoms | Binance: top {limit} coins")
        return total


class GitHubSource:
    BASE_URL = "https://api.github.com"

    def __init__(self, engine: NoesisEngine) -> None:
        self.engine = engine
        self.token = os.environ.get("GITHUB_TOKEN", "")

    def trending(self, language: str = "", max_results: int = 5) -> int:
        query = "stars:>1000 pushed:>2026-01-01"
        if language:
            query += f" language:{language}"
        headers = {"Accept": "application/vnd.github.v3+json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        resp = _http_get(
            f"{self.BASE_URL}/search/repositories",
            headers=headers,
            params={"q": query, "sort": "updated", "per_page": str(max_results)},
        )
        if resp is None:
            return 0
        total = 0
        items = resp.json().get("items", [])
        for repo in items:
            name = repo.get("full_name", "")
            desc = repo.get("description", "")
            stars = repo.get("stargazers_count", 0)
            lang = repo.get("language", "")
            if desc and len(desc) > 20:
                text = (
                    f"{name} is a {lang} project on GitHub with {stars:,} stars. "
                    f"{desc}"
                )
                added = self.engine.learn(text, source=f"github:{name}")
                total += added
                if added > 0:
                    print(f"  +{added:4d} atoms | GitHub: {name}")
        return total

    def search_repos(self, query: str, max_results: int = 5) -> int:
        headers = {"Accept": "application/vnd.github.v3+json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        resp = _http_get(
            f"{self.BASE_URL}/search/repositories",
            headers=headers,
            params={"q": query, "sort": "stars", "per_page": str(max_results)},
        )
        if resp is None:
            return 0
        total = 0
        items = resp.json().get("items", [])
        for repo in items:
            name = repo.get("full_name", "")
            desc = repo.get("description", "")
            stars = repo.get("stargazers_count", 0)
            lang = repo.get("language", "")
            if desc and len(desc) > 20:
                text = f"{name} is a {lang} project with {stars:,} stars. {desc}"
                added = self.engine.learn(text, source=f"github:{query}")
                total += added
                if added > 0:
                    print(f"  +{added:4d} atoms | GitHub: {name}")
        return total


class CustomAPISource:
    def __init__(self, engine: NoesisEngine) -> None:
        self.engine = engine

    def fetch(self, url: str, text_field: str = "text", items_field: str = "") -> int:
        resp = _http_get(url)
        if resp is None:
            return 0
        total = 0
        data = resp.json()
        if items_field and isinstance(data, dict):
            items = data.get(items_field, [])
        elif isinstance(data, list):
            items = data
        else:
            items = [data]
        for item in items[:20]:
            if isinstance(item, dict):
                text = item.get(text_field, "")
                if not text:
                    text = item.get("description", item.get("summary", item.get("content", "")))
            elif isinstance(item, str):
                text = item
            else:
                continue
            text = _strip_html(str(text))
            if text and len(text) > 50:
                added = self.engine.learn(text, source=f"api:{url[:40]}")
                total += added
        if total > 0:
            print(f"  +{total:4d} atoms | API: {url[:60]}")
        return total


def main() -> None:
    parser = argparse.ArgumentParser(description="Νόηση Ingest — Knowledge Sources")
    parser.add_argument("--scan", type=Path, help="Scan directory for text files")
    parser.add_argument("--recursive", action="store_true", help="Recursive directory scan")
    parser.add_argument("--nasa", action="store_true", help="NASA Astronomy Picture of the Day")
    parser.add_argument("--nasa-count", type=int, default=5, help="Number of APOD entries")
    parser.add_argument("--nasa-search", type=str, help="Search NASA image library")
    parser.add_argument("--arxiv", type=str, help="Search Arxiv papers")
    parser.add_argument("--arxiv-count", type=int, default=5)
    parser.add_argument("--wiki", type=str, help="Wikipedia topic lookup")
    parser.add_argument("--rss", type=str, help="Single RSS feed URL")
    parser.add_argument("--feeds", action="store_true", help="Fetch all configured RSS feeds")
    parser.add_argument("--api", type=str, help="Custom JSON API URL")
    parser.add_argument("--nasa-ads", type=str, help="Search NASA ADS papers")
    parser.add_argument("--binance", action="store_true", help="Top crypto coins from Binance")
    parser.add_argument("--github", type=str, help="Search GitHub repos")
    parser.add_argument("--github-trending", action="store_true", help="Trending GitHub repos")
    parser.add_argument("--all", action="store_true", help="Run all sources")
    parser.add_argument("--lattice", type=Path, default=LATTICE_PATH)
    args = parser.parse_args()

    engine = NoesisEngine()
    if args.lattice.exists():
        loaded = engine.load(args.lattice)
        print(f"  Loaded {loaded} atoms from lattice\n")
    else:
        print(f"  Starting with empty lattice\n")

    t0 = time.perf_counter()
    total_atoms = 0

    if args.scan:
        print(f"═══ Scanning: {args.scan} ═══\n")
        scanner = FileScanner(engine)
        files, atoms = scanner.scan(args.scan, recursive=args.recursive)
        total_atoms += atoms
        print(f"\n  {files} files, {atoms} atoms\n")

    if args.nasa or args.all:
        print(f"═══ NASA APOD ═══\n")
        nasa = NasaSource(engine)
        atoms = nasa.apod(count=args.nasa_count)
        total_atoms += atoms
        print()

    if args.nasa_search:
        print(f"═══ NASA Search: {args.nasa_search} ═══\n")
        nasa = NasaSource(engine)
        atoms = nasa.search(args.nasa_search)
        total_atoms += atoms
        print()

    if args.arxiv:
        print(f"═══ Arxiv: {args.arxiv} ═══\n")
        arxiv = ArxivSource(engine)
        atoms = arxiv.search(args.arxiv, max_results=args.arxiv_count)
        total_atoms += atoms
        print()

    if args.wiki:
        print(f"═══ Wikipedia: {args.wiki} ═══\n")
        wiki = WikipediaSource(engine)
        atoms = wiki.lookup(args.wiki)
        total_atoms += atoms
        print()

    if args.rss:
        print(f"═══ RSS Feed ═══\n")
        rss = RSSSource(engine)
        atoms = rss.fetch_feed(args.rss, max_items=10)
        total_atoms += atoms
        print()

    if args.feeds or args.all:
        print(f"═══ RSS Feeds ({len(RSS_FEEDS)} configured) ═══")
        rss = RSSSource(engine)
        atoms = rss.fetch_all(max_items=5)
        total_atoms += atoms
        print()

    if args.api:
        print(f"═══ Custom API ═══\n")
        api = CustomAPISource(engine)
        atoms = api.fetch(args.api)
        total_atoms += atoms
        print()

    if args.nasa_ads:
        print(f"═══ NASA ADS: {args.nasa_ads} ═══\n")
        ads = NasaADSSource(engine)
        atoms = ads.search(args.nasa_ads)
        total_atoms += atoms
        print()

    if args.binance or args.all:
        print(f"═══ Binance Top Coins ═══\n")
        binance = BinanceSource(engine)
        atoms = binance.top_coins(limit=10)
        total_atoms += atoms
        print()

    if args.github:
        print(f"═══ GitHub: {args.github} ═══\n")
        gh = GitHubSource(engine)
        atoms = gh.search_repos(args.github)
        total_atoms += atoms
        print()

    if args.github_trending or args.all:
        print(f"═══ GitHub Trending ═══\n")
        gh = GitHubSource(engine)
        atoms = gh.trending(max_results=5)
        total_atoms += atoms
        print()

    if total_atoms == 0 and not any([args.scan, args.nasa, args.nasa_search, args.arxiv, args.wiki, args.rss, args.feeds, args.api, args.nasa_ads, args.binance, args.github, args.github_trending, args.all]):
        print("  No source specified. Use --help for options.\n")
        return

    elapsed = time.perf_counter() - t0
    before = engine.lattice.size
    evo = engine.evolve()
    engine.save(args.lattice)

    print(f"═══ Summary ═══\n")
    print(f"  New atoms: {total_atoms}")
    print(f"  Evolution: {evo.pruned} pruned, {evo.merged} merged")
    print(f"  Lattice: {before} → {engine.lattice.size} atoms")
    print(f"  Time: {elapsed:.1f}s")
    print(f"  Saved to: {args.lattice}\n")


if __name__ == "__main__":
    main()
