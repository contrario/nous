"""
Noesis Wikipedia Bulk Ingestion
Fetches curated Wikipedia summaries per domain.
"""
from __future__ import annotations
import logging
import time
from pathlib import Path
from typing import Any
import httpx

log = logging.getLogger("nous.wiki_bulk")

WIKI_API = "https://en.wikipedia.org/api/rest_v1/page/summary"
WIKI_HEADERS = {
    "User-Agent": "Noesis/1.0 (NOUS Project; Athens, Greece)",
    "Accept": "application/json",
}

TOPICS: dict[str, list[str]] = {
    "cooking": [
        "Maillard_reaction", "Caramelization", "Mise_en_place", "Sous_vide",
        "Emulsion", "Fermentation_in_food_processing", "Braise", "Blanching_(cooking)",
        "Deglazing_(cooking)", "Roux", "Béchamel_sauce", "Hollandaise_sauce",
        "Mother_sauce", "Sautéing", "Poaching_(cooking)", "Confit",
        "Chiffonade", "Julienne", "Brunoise", "Mirepoix_(cooking)",
        "Bouquet_garni", "Demi-glace", "Reduction_(cooking)", "Fond_(food)",
        "Umami", "Food_preservation", "Curing_(food_preservation)", "Smoking_(cooking)",
        "Pickling", "Sourdough", "Gluten", "Leavening_agent",
        "Custard", "Meringue", "Ganache", "Tempering_(chocolate)",
        "Olive_oil", "Balsamic_vinegar", "Saffron", "Vanilla",
        "Mediterranean_diet", "French_cuisine", "Italian_cuisine", "Greek_cuisine",
        "Japanese_cuisine", "Knife_skills", "Food_safety", "HACCP",
        "Pasteurization", "Molecular_gastronomy", "Spherification", "Foam_(food)",
        "Gelatin", "Agar", "Pectin", "Starch",
        "Clarified_butter", "Ghee", "Rendered_fat", "Lard",
        "Brine_(food)", "Marinade", "Dry_rub", "Spice_mix",
        "Herb", "Bay_leaf", "Oregano", "Basil",
        "Thyme", "Rosemary", "Cinnamon", "Cumin",
        "Paprika", "Turmeric", "Coriander_(spice)", "Nutmeg",
    ],
    "finance": [
        "Stock_market", "Bond_(finance)", "Exchange-traded_fund",
        "Mutual_fund", "Hedge_fund", "Index_fund", "Dividend",
        "Price-to-earnings_ratio", "Market_capitalization", "Initial_public_offering",
        "Compound_interest", "Inflation", "Deflation", "Recession",
        "Gross_domestic_product", "Federal_Reserve", "European_Central_Bank",
        "Monetary_policy", "Fiscal_policy", "Quantitative_easing",
        "Balance_sheet", "Income_statement", "Cash_flow_statement",
        "Asset_allocation", "Portfolio_(finance)", "Diversification_(finance)",
        "Risk_management", "Value_investing", "Growth_investing",
        "Technical_analysis", "Fundamental_analysis", "Efficient-market_hypothesis",
        "Black–Scholes_model", "Option_(finance)", "Futures_contract",
        "Foreign_exchange_market", "Cryptocurrency", "Bitcoin", "Ethereum",
        "Blockchain", "Decentralized_finance", "Smart_contract",
        "Venture_capital", "Private_equity", "Angel_investor",
        "Credit_score", "Mortgage_loan", "Amortization_(business)",
        "Retirement_planning", "401(k)", "Individual_retirement_account",
    ],
    "science": [
        "Quantum_mechanics", "General_relativity", "Standard_Model",
        "Thermodynamics", "Entropy", "Electromagnetism",
        "Photosynthesis", "Cellular_respiration", "DNA_replication",
        "CRISPR_gene_editing", "Protein_folding", "Enzyme",
        "Natural_selection", "Genetic_drift", "Speciation",
        "Plate_tectonics", "Volcanic_eruption", "Earthquake",
        "Climate_change", "Greenhouse_effect", "Carbon_cycle",
        "Black_hole", "Neutron_star", "Exoplanet",
        "Big_Bang", "Dark_matter", "Dark_energy",
        "Periodic_table", "Chemical_bond", "Organic_chemistry",
        "Neuroscience", "Synapse", "Neurotransmitter",
        "Immune_system", "Vaccine", "Antibiotic",
        "Stem_cell", "Mitosis", "Meiosis",
        "Higgs_boson", "Superconductivity", "Laser",
        "Nuclear_fusion", "Nuclear_fission", "Radioactive_decay",
        "Theory_of_evolution", "Fossil_record", "Phylogenetics",
        "Hubble_Space_Telescope", "James_Webb_Space_Telescope", "LIGO",
    ],
}

def ingest_wikipedia(engine: Any, domain: str, topics: list[str]) -> dict[str, int]:
    success = 0
    failed = 0
    total_atoms = 0
    for topic in topics:
        slug = topic.replace(" ", "_")
        try:
            with httpx.Client(timeout=15, follow_redirects=True) as client:
                resp = client.get(f"{WIKI_API}/{slug}", headers=WIKI_HEADERS)
                if resp.status_code != 200:
                    log.warning(f"Wiki {slug}: HTTP {resp.status_code}")
                    failed += 1
                    continue
                data = resp.json()
                extract = data.get("extract", "")
                if not extract or len(extract) < 50:
                    log.warning(f"Wiki {slug}: too short")
                    failed += 1
                    continue
                added = engine.learn(extract, source=f"wikipedia:{slug}")
                total_atoms += added
                success += 1
                log.info(f"Wiki {slug}: +{added} atoms")
        except Exception as e:
            log.warning(f"Wiki {slug}: {e}")
            failed += 1
        time.sleep(0.3)
    return {"domain": domain, "topics": success, "failed": failed, "atoms": total_atoms}


def run_all(engine: Any) -> list[dict[str, int]]:
    results = []
    for domain, topics in TOPICS.items():
        print(f"\n{'='*50}")
        print(f"  Domain: {domain} — {len(topics)} topics")
        print(f"{'='*50}")
        r = ingest_wikipedia(engine, domain, topics)
        print(f"  Result: {r['topics']} OK, {r['failed']} failed, +{r['atoms']} atoms")
        results.append(r)
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
    from noesis_engine import NoesisEngine
    from noesis_oracle import create_oracle_fn
    oracle_fn, _ = create_oracle_fn()
    engine = NoesisEngine(oracle_fn=oracle_fn, oracle_threshold=0.55)
    lp = Path("/opt/aetherlang_agents/nous/noesis_lattice.json")
    if lp.exists():
        engine.load(lp)
        print(f"Loaded {engine.lattice.size} atoms")
    results = run_all(engine)
    engine.save(lp)
    print(f"\n{'='*50}")
    print(f"  DONE — Lattice: {engine.lattice.size} atoms")
    for r in results:
        print(f"  {r['domain']}: +{r['atoms']} atoms ({r['topics']} topics)")
    print(f"{'='*50}")
