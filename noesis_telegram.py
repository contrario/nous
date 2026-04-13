"""
Νόηση Telegram Bridge — Ερμής (Hermes)
=========================================
Connects Noesis to Telegram. Users ask questions, Noesis answers.
When she doesn't know, she asks oracle, learns, and answers.

Also includes extra free knowledge APIs.

Usage:
    python3 noesis_telegram.py                 # Run bot (foreground)
    nohup python3 noesis_telegram.py &         # Run bot (daemon)
    python3 noesis_telegram.py --test "query"  # Test without Telegram

Cron (auto-restart if crashed):
    */5 * * * * pgrep -f noesis_telegram.py || cd /opt/aetherlang_agents/nous && nohup python3 noesis_telegram.py >> /var/log/noesis_telegram.log 2>&1 &

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
from noesis_oracle import create_oracle_fn

log = logging.getLogger("nous.telegram")

LATTICE_PATH = Path("/opt/aetherlang_agents/nous/noesis_lattice.json")
ENV_PATH = Path("/opt/aetherlang_agents/.env")
POLL_INTERVAL: float = 1.5
HTTP_TIMEOUT: float = 20.0


def _load_env() -> None:
    if not ENV_PATH.exists():
        return
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and value and key not in os.environ:
            os.environ[key] = value


_load_env()


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


class ExtraKnowledge:
    def __init__(self, engine: NoesisEngine) -> None:
        self.engine = engine

    def weather(self, city: str) -> str:
        geocode = _http_get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": "1"},
        )
        if geocode is None:
            return ""
        results = geocode.json().get("results", [])
        if not results:
            return f"City not found: {city}"
        lat = results[0]["latitude"]
        lon = results[0]["longitude"]
        name = results[0]["name"]
        resp = _http_get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": str(lat),
                "longitude": str(lon),
                "current": "temperature_2m,wind_speed_10m,relative_humidity_2m,weather_code",
            },
        )
        if resp is None:
            return ""
        current = resp.json().get("current", {})
        temp = current.get("temperature_2m", "?")
        wind = current.get("wind_speed_10m", "?")
        humidity = current.get("relative_humidity_2m", "?")
        text = f"Weather in {name}: {temp}°C, wind {wind} km/h, humidity {humidity}%."
        self.engine.learn(text, source=f"weather:{city}")
        return text

    def country(self, name: str) -> str:
        resp = _http_get(f"https://restcountries.com/v3.1/name/{name}")
        if resp is None:
            return ""
        data = resp.json()
        if not data or not isinstance(data, list):
            return ""
        c = data[0]
        common = c.get("name", {}).get("common", name)
        capital = ", ".join(c.get("capital", []))
        pop = c.get("population", 0)
        region = c.get("region", "")
        languages = ", ".join(c.get("languages", {}).values())
        text = (
            f"{common} is a country in {region} with a population of {pop:,}. "
            f"The capital is {capital}. Languages spoken include {languages}."
        )
        self.engine.learn(text, source=f"country:{name}")
        return text

    def define(self, word: str) -> str:
        resp = _http_get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}")
        if resp is None:
            return ""
        data = resp.json()
        if not data or not isinstance(data, list):
            return ""
        meanings = data[0].get("meanings", [])
        parts: list[str] = []
        for m in meanings[:2]:
            pos = m.get("partOfSpeech", "")
            defs = m.get("definitions", [])
            if defs:
                definition = defs[0].get("definition", "")
                parts.append(f"{word} ({pos}): {definition}")
        text = ". ".join(parts)
        if text:
            self.engine.learn(text, source=f"dictionary:{word}")
        return text

    def earthquake(self) -> str:
        resp = _http_get(
            "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/significant_month.geojson"
        )
        if resp is None:
            return ""
        features = resp.json().get("features", [])[:3]
        parts: list[str] = []
        for f in features:
            props = f.get("properties", {})
            place = props.get("place", "Unknown")
            mag = props.get("mag", 0)
            parts.append(f"Magnitude {mag} earthquake near {place}.")
        text = " ".join(parts)
        if text:
            self.engine.learn(text, source="usgs:earthquakes")
        return text

    def crypto(self, coin: str = "bitcoin") -> str:
        resp = _http_get(
            f"https://api.coingecko.com/api/v3/simple/price",
            params={"ids": coin, "vs_currencies": "usd,eur", "include_24hr_change": "true"},
        )
        if resp is None:
            return ""
        data = resp.json().get(coin, {})
        usd = data.get("usd", 0)
        eur = data.get("eur", 0)
        change = data.get("usd_24h_change", 0)
        direction = "up" if change > 0 else "down"
        text = f"{coin.title()} is currently ${usd:,.2f} (€{eur:,.2f}), {direction} {abs(change):.1f}% in the last 24 hours."
        self.engine.learn(text, source=f"crypto:{coin}")
        return text

    def food(self, query: str) -> str:
        resp = _http_get(
            "https://world.openfoodfacts.org/cgi/search.pl",
            params={"search_terms": query, "json": "1", "page_size": "3"},
        )
        if resp is None:
            return ""
        products = resp.json().get("products", [])[:3]
        parts: list[str] = []
        for p in products:
            name = p.get("product_name", "")
            brand = p.get("brands", "")
            nutri = p.get("nutriscore_grade", "?")
            if name:
                parts.append(f"{name} by {brand} has a Nutri-Score of {nutri.upper()}.")
        text = " ".join(parts)
        if text:
            self.engine.learn(text, source=f"food:{query}")
        return text

    def pubmed(self, query: str, max_results: int = 3) -> str:
        search_resp = _http_get(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
            params={"db": "pubmed", "term": query, "retmax": str(max_results), "retmode": "json"},
        )
        if search_resp is None:
            return ""
        ids = search_resp.json().get("esearchresult", {}).get("idlist", [])
        if not ids:
            return ""
        fetch_resp = _http_get(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
            params={"db": "pubmed", "id": ",".join(ids), "retmode": "json"},
        )
        if fetch_resp is None:
            return ""
        result = fetch_resp.json().get("result", {})
        parts: list[str] = []
        for uid in ids:
            article = result.get(uid, {})
            title = article.get("title", "")
            source = article.get("source", "")
            pubdate = article.get("pubdate", "")
            if title:
                parts.append(f"{title} Published in {source}, {pubdate}.")
        text = " ".join(parts)
        if text:
            self.engine.learn(text, source=f"pubmed:{query}")
        return text


COMMANDS: dict[str, str] = {
    "/think": "Ask Noesis a question",
    "/learn": "Teach Noesis new knowledge",
    "/weather": "Get weather for a city",
    "/country": "Get country info",
    "/define": "Define a word",
    "/crypto": "Get crypto price",
    "/quake": "Recent significant earthquakes",
    "/food": "Search food nutrition",
    "/pubmed": "Search medical papers",
    "/wiki": "Learn from Wikipedia",
    "/stats": "Show Noesis statistics",
    "/evolve": "Run lattice evolution",
    "/save": "Save lattice to disk",
    "/help": "Show this help",
}


class TelegramBot:
    def __init__(
        self,
        token: str,
        chat_id: str,
        engine: NoesisEngine,
        extra: ExtraKnowledge,
    ) -> None:
        self.token = token
        self.chat_id = chat_id
        self.engine = engine
        self.extra = extra
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.last_update_id: int = 0

    def send(self, text: str, chat_id: str = "") -> None:
        cid = chat_id or self.chat_id
        try:
            with httpx.Client(timeout=10) as client:
                client.post(
                    f"{self.base_url}/sendMessage",
                    json={
                        "chat_id": cid,
                        "text": text[:4000],
                        "parse_mode": "Markdown",
                    },
                )
        except Exception as e:
            log.warning(f"Telegram send failed: {e}")
            try:
                with httpx.Client(timeout=10) as client:
                    client.post(
                        f"{self.base_url}/sendMessage",
                        json={"chat_id": cid, "text": text[:4000]},
                    )
            except Exception:
                pass

    def get_updates(self) -> list[dict[str, Any]]:
        try:
            with httpx.Client(timeout=30) as client:
                resp = client.get(
                    f"{self.base_url}/getUpdates",
                    params={"offset": str(self.last_update_id + 1), "timeout": "20"},
                )
                data = resp.json()
                return data.get("result", [])
        except Exception as e:
            log.warning(f"Telegram getUpdates failed: {e}")
            return []

    def handle_message(self, text: str, chat_id: str) -> None:
        text = text.strip()
        if not text:
            return

        if text == "/help" or text == "/start":
            lines = ["🧠 *Νόηση — Symbolic Intelligence*\n"]
            for cmd, desc in COMMANDS.items():
                lines.append(f"`{cmd}` — {desc}")
            self.send("\n".join(lines), chat_id)
            return

        if text == "/stats":
            s = self.engine.stats()
            msg = (
                f"🧠 *Νόηση Stats*\n"
                f"Atoms: {s['atoms']}\n"
                f"Autonomy: {s['autonomy']}\n"
                f"Queries: {s['queries']}\n"
                f"Oracle calls: {s['oracle_calls']}\n"
                f"Confidence: {s['avg_confidence']:.2f}\n"
                f"Patterns: {s['unique_patterns']}\n"
                f"Relations: {s['unique_relations']}"
            )
            self.send(msg, chat_id)
            return

        if text == "/evolve":
            evo = self.engine.evolve()
            self.send(f"🧬 Pruned: {evo.pruned} | Merged: {evo.merged} | Lattice: {self.engine.lattice.size}", chat_id)
            return

        if text == "/save":
            self.engine.save(LATTICE_PATH)
            self.send(f"💾 Saved {self.engine.lattice.size} atoms", chat_id)
            return

        if text == "/quake":
            result = self.extra.earthquake()
            self.send(f"🌍 {result}" if result else "No recent significant earthquakes.", chat_id)
            return

        if text.startswith("/think "):
            query = text[7:].strip()
            result = self.engine.think(query, mode="compose", top_k=5, use_oracle=True)
            oracle_tag = " 🔮" if result.oracle_used else " 🧠"
            self.send(f"{result.response}\n\n_{result.atoms_matched} atoms | {result.top_score:.2f} | {result.elapsed_ms:.0f}ms{oracle_tag}_", chat_id)
            return

        if text.startswith("/learn "):
            content = text[7:].strip()
            added = self.engine.learn(content, source="telegram")
            self.send(f"📚 +{added} atoms | Lattice: {self.engine.lattice.size}", chat_id)
            return

        if text.startswith("/weather "):
            city = text[9:].strip()
            result = self.extra.weather(city)
            self.send(f"🌤️ {result}" if result else f"Weather not found for {city}", chat_id)
            return

        if text.startswith("/country "):
            name = text[9:].strip()
            result = self.extra.country(name)
            self.send(f"🌍 {result}" if result else f"Country not found: {name}", chat_id)
            return

        if text.startswith("/define "):
            word = text[8:].strip()
            result = self.extra.define(word)
            self.send(f"📖 {result}" if result else f"Definition not found: {word}", chat_id)
            return

        if text.startswith("/crypto"):
            coin = text[8:].strip() if len(text) > 8 else "bitcoin"
            result = self.extra.crypto(coin.lower())
            self.send(f"💰 {result}" if result else f"Coin not found: {coin}", chat_id)
            return

        if text.startswith("/food "):
            query = text[6:].strip()
            result = self.extra.food(query)
            self.send(f"🍽️ {result}" if result else f"No results for: {query}", chat_id)
            return

        if text.startswith("/pubmed "):
            query = text[8:].strip()
            result = self.extra.pubmed(query)
            self.send(f"🔬 {result}" if result else f"No results for: {query}", chat_id)
            return

        if text.startswith("/wiki "):
            topic = text[6:].strip()
            slug = topic.replace(" ", "_")
            resp = _http_get(
                f"https://en.wikipedia.org/api/rest_v1/page/summary/{slug}",
                headers={"User-Agent": "Noesis/1.0 (NOUS Project; Athens, Greece)", "Accept": "application/json"},
            )
            if resp:
                extract = resp.json().get("extract", "")
                if extract:
                    added = self.engine.learn(extract, source=f"wikipedia:{topic}")
                    self.send(f"📚 Learned {added} atoms from Wikipedia: {topic}", chat_id)
                else:
                    self.send(f"No Wikipedia article found for: {topic}", chat_id)
            else:
                self.send(f"Wikipedia lookup failed for: {topic}", chat_id)
            return

        result = self.engine.think(text, mode="compose", top_k=5, use_oracle=True)
        if result.response:
            oracle_tag = " 🔮" if result.oracle_used else " 🧠"
            self.send(f"{result.response}\n\n_{result.atoms_matched} atoms | {result.top_score:.2f} | {result.elapsed_ms:.0f}ms{oracle_tag}_", chat_id)
        else:
            self.send("🤔 I don't know. Try `/learn` to teach me.", chat_id)

    def run(self) -> None:
        print(f"  🧠 Νόηση Telegram Bot running...")
        print(f"  Lattice: {self.engine.lattice.size} atoms")
        print(f"  Chat ID: {self.chat_id}")
        print(f"  Ctrl+C to stop\n")

        self.send("🧠 Νόηση online. /help for commands.")

        while True:
            try:
                updates = self.get_updates()
                for update in updates:
                    self.last_update_id = update["update_id"]
                    msg = update.get("message", {})
                    text = msg.get("text", "")
                    chat_id = str(msg.get("chat", {}).get("id", self.chat_id))
                    if text:
                        log.info(f"[{chat_id}] {text[:100]}")
                        self.handle_message(text, chat_id)
                time.sleep(POLL_INTERVAL)
            except KeyboardInterrupt:
                print("\n  Saving lattice...")
                self.engine.save(LATTICE_PATH)
                print(f"  Saved {self.engine.lattice.size} atoms. Αντίο.")
                break
            except Exception as e:
                log.error(f"Bot error: {e}")
                time.sleep(5)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(description="Νόηση Telegram Bot")
    parser.add_argument("--test", type=str, help="Test query without Telegram")
    parser.add_argument("--lattice", type=Path, default=LATTICE_PATH)
    args = parser.parse_args()

    oracle_fn, oracle = create_oracle_fn()
    engine = NoesisEngine(oracle_fn=oracle_fn, oracle_threshold=0.3)

    if args.lattice.exists():
        loaded = engine.load(args.lattice)
        print(f"  Loaded {loaded} atoms")

    extra = ExtraKnowledge(engine)

    if args.test:
        result = engine.think(args.test, mode="compose", top_k=5, use_oracle=True)
        oracle_tag = " [oracle]" if result.oracle_used else ""
        print(f"\n  {result.response}\n")
        print(f"  [{result.atoms_matched} atoms | score={result.top_score:.3f} | {result.elapsed_ms:.1f}ms{oracle_tag}]")
        engine.save(args.lattice)
        return

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    if not token:
        print("  Error: TELEGRAM_BOT_TOKEN not set in .env")
        return
    if not chat_id:
        print("  Error: TELEGRAM_CHAT_ID not set in .env")
        return

    bot = TelegramBot(token=token, chat_id=chat_id, engine=engine, extra=extra)
    bot.run()


if __name__ == "__main__":
    main()
