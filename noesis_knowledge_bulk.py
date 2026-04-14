"""
Noesis Knowledge Bulk Ingestion — Phase B
==========================================
Sources: CERN Glossary, Wikipedia (health, history, law, physics, philosophy)
Author: Hlias Staurou + Claude | NOUS Project | April 2026
"""
from __future__ import annotations
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, "/opt/aetherlang_agents/nous")
from noesis_engine import NoesisEngine
from noesis_oracle import create_oracle_fn

log = logging.getLogger("nous.bulk")
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(name)s | %(message)s", datefmt="%H:%M:%S")

LATTICE = Path("/opt/aetherlang_agents/nous/noesis_lattice.json")
WIKI_HEADERS = {"User-Agent": "NoesisBot/1.0 (hlia@nous-project.org)"}


def fetch_cern_glossary() -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    page = 1
    while True:
        url = f"https://opendata.cern.ch/api/records/?page={page}&size=50&q=&type=Glossary"
        try:
            resp = httpx.get(url, timeout=20)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            log.warning(f"CERN page {page} failed: {e}")
            break
        hits = data.get("hits", {}).get("hits", [])
        if not hits:
            break
        for h in hits:
            meta = h.get("metadata", {})
            title = meta.get("title", "")
            abstract = meta.get("abstract", {}).get("description", "")
            if title and abstract and len(abstract) > 30:
                entries.append({"title": title, "text": f"{title}: {abstract}"})
        page += 1
        time.sleep(0.5)
    return entries


def fetch_wikipedia(title: str, lang: str = "en") -> str:
    url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{title}"
    try:
        resp = httpx.get(url, headers=WIKI_HEADERS, timeout=15, follow_redirects=True)
        if resp.status_code == 200:
            data = resp.json()
            extract = data.get("extract", "")
            if len(extract) > 50:
                return extract
    except Exception as e:
        log.warning(f"Wiki {lang}/{title} failed: {e}")
    return ""


WIKI_TOPICS: dict[str, list[str]] = {
    "health": [
        "Immune_system", "Cardiovascular_disease", "Diabetes", "Cancer",
        "Nutrition", "Vitamin", "Antibiotic", "Vaccine", "Mental_health",
        "Sleep", "Exercise", "Obesity", "Hypertension", "Allergy",
        "Inflammation", "Metabolism", "Gut_microbiota", "Cholesterol",
        "Anxiety_disorder", "Depression_(mood)", "Alzheimer%27s_disease",
        "Parkinson%27s_disease", "Asthma", "Arthritis", "Osteoporosis",
    ],
    "history": [
        "Ancient_Greece", "Roman_Empire", "Byzantine_Empire", "Ottoman_Empire",
        "French_Revolution", "Industrial_Revolution", "World_War_I",
        "World_War_II", "Cold_War", "Renaissance", "Enlightenment",
        "Greek_War_of_Independence", "Alexander_the_Great", "Democracy",
        "Silk_Road", "Scientific_Revolution", "Age_of_Discovery",
        "Fall_of_Constantinople", "Ancient_Rome", "Ancient_Egypt",
    ],
    "law": [
        "Rule_of_law", "Constitution", "Human_rights", "Contract_law",
        "Criminal_law", "Civil_law_(legal_system)", "International_law",
        "European_Union_law", "Intellectual_property", "Copyright",
        "Patent", "Tort", "Due_process", "Habeas_corpus",
        "Freedom_of_speech", "Privacy_law", "Labour_law",
    ],
    "physics": [
        "Quantum_mechanics", "General_relativity", "Standard_Model",
        "Higgs_boson", "Dark_matter", "Dark_energy", "Black_hole",
        "Neutron_star", "Superconductivity", "Electromagnetism",
        "Nuclear_fusion", "Nuclear_fission", "Antimatter", "Neutrino",
        "Gravitational_wave", "String_theory", "Entropy",
        "Schrödinger_equation", "Wave–particle_duality", "Photoelectric_effect",
    ],
    "philosophy": [
        "Epistemology", "Ethics", "Metaphysics", "Logic",
        "Socrates", "Plato", "Aristotle", "Stoicism", "Existentialism",
        "Phenomenology_(philosophy)", "Utilitarianism", "Categorical_imperative",
        "Free_will", "Consciousness", "Philosophy_of_mind",
        "Philosophy_of_science", "Aesthetics", "Political_philosophy",
    ],
    "history_gr": [
        "Αρχαία_Ελλάδα", "Βυζαντινή_Αυτοκρατορία", "Ελληνική_Επανάσταση_του_1821",
        "Μέγας_Αλέξανδρος", "Δημοκρατία", "Αθηναϊκή_δημοκρατία",
        "Πελοποννησιακός_πόλεμος", "Περικλής", "Σωκράτης", "Πλάτων",
        "Αριστοτέλης", "Ολυμπιακοί_Αγώνες",
    ],
}


def main() -> None:
    oracle_fn, oracle = create_oracle_fn()
    engine = NoesisEngine(oracle_fn=oracle_fn, oracle_threshold=0.55)
    engine.load(LATTICE)
    before = engine.lattice.size
    log.info(f"Before: {before} atoms")

    log.info("=== CERN Glossary ===")
    cern = fetch_cern_glossary()
    cern_added = 0
    for entry in cern:
        n = engine.learn(entry["text"], source="cern-glossary")
        cern_added += n
    log.info(f"CERN: {len(cern)} entries → +{cern_added} atoms")

    log.info("=== Wikipedia ===")
    wiki_total = 0
    for domain, topics in WIKI_TOPICS.items():
        lang = "el" if domain.endswith("_gr") else "en"
        domain_added = 0
        success = 0
        for title in topics:
            text = fetch_wikipedia(title, lang=lang)
            if text:
                n = engine.learn(text, source=f"wikipedia-{domain}")
                domain_added += n
                success += 1
            time.sleep(0.3)
        log.info(f"  {domain}: {success}/{len(topics)} → +{domain_added} atoms")
        wiki_total += domain_added

    after = engine.lattice.size
    log.info(f"Total new: +{after - before} (CERN: {cern_added}, Wiki: {wiki_total})")
    log.info(f"After: {after} atoms")
    engine.save(LATTICE)
    log.info("Saved.")


if __name__ == "__main__":
    main()
