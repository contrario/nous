"""
Νόηση (Noesis) — The Thinking Engine
======================================
A symbolic reasoning engine that replaces neural weights with compressed
knowledge atoms. No GPU. No billions of parameters. Pure algorithmic intelligence.

Architecture:
    Text → Compress → Atoms → Lattice (knowledge)
    Query → Resonate → Atoms → Weave → Response
    Usage → Evolve → Prune/Merge/Mutate → Better Lattice

Core principle: Intelligence is compression.
    - A neural network stores "Paris is the capital of France" across millions of weights.
    - Noesis stores it as one Atom: {pattern: [paris, capital, france], template: "{subject} is the capital of {object}"}
    - The atom is infinitely more efficient. The question is composition at scale.

Author: Hlias Staurou + Claude | NOUS Project | April 2026
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Callable


@dataclass
class Atom:
    id: str
    patterns: list[str]
    relations: dict[str, str] = field(default_factory=dict)
    template: str = ""
    level: int = 2
    confidence: float = 1.0
    usage_count: int = 0
    success_count: int = 0
    birth: float = field(default_factory=time.time)
    source: str = "compression"
    tags: set[str] = field(default_factory=set)

    @property
    def fitness(self) -> float:
        if self.usage_count == 0:
            return self.confidence * 0.5
        success_rate = self.success_count / max(self.usage_count, 1)
        age_factor = min(1.0, (time.time() - self.birth) / 86400)
        return (self.confidence * 0.4 + success_rate * 0.4 + age_factor * 0.2)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "patterns": self.patterns,
            "relations": self.relations,
            "template": self.template,
            "level": self.level,
            "confidence": self.confidence,
            "usage_count": self.usage_count,
            "success_count": self.success_count,
            "birth": self.birth,
            "source": self.source,
            "tags": list(self.tags),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Atom:
        d = dict(d)
        d["tags"] = set(d.get("tags", []))
        return cls(**d)


class TrieNode:
    __slots__ = ("children", "atom_ids")

    def __init__(self) -> None:
        self.children: dict[str, TrieNode] = {}
        self.atom_ids: set[str] = set()

    def insert(self, tokens: list[str], atom_id: str) -> None:
        node = self
        for token in tokens:
            if token not in node.children:
                node.children[token] = TrieNode()
            node = node.children[token]
            node.atom_ids.add(atom_id)

    def search(self, tokens: list[str]) -> set[str]:
        results: set[str] = set()
        node = self
        for token in tokens:
            if token in node.children:
                node = node.children[token]
                results.update(node.atom_ids)
            else:
                break
        return results

    def search_all_prefixes(self, tokens: list[str]) -> set[str]:
        results: set[str] = set()
        for i in range(len(tokens)):
            results.update(self.search(tokens[i:]))
        return results

    def remove(self, tokens: list[str], atom_id: str) -> None:
        node = self
        for token in tokens:
            if token not in node.children:
                return
            node = node.children[token]
            node.atom_ids.discard(atom_id)


class Lattice:
    def __init__(self) -> None:
        self.atoms: dict[str, Atom] = {}
        self.trie: TrieNode = TrieNode()
        self.inverted: dict[str, set[str]] = defaultdict(set)
        self.concepts: dict[str, set[str]] = defaultdict(set)
        self.relation_index: dict[str, set[str]] = defaultdict(set)

    def add(self, atom: Atom) -> None:
        self.atoms[atom.id] = atom
        self.trie.insert(atom.patterns, atom.id)
        for pattern in atom.patterns:
            self.inverted[pattern.lower()].add(atom.id)
        for key, value in atom.relations.items():
            self.relation_index[f"{key}:{value}"].add(atom.id)
        for tag in atom.tags:
            self.concepts[tag].add(atom.id)

    def remove(self, atom_id: str) -> Optional[Atom]:
        atom = self.atoms.pop(atom_id, None)
        if atom is None:
            return None
        self.trie.remove(atom.patterns, atom_id)
        for pattern in atom.patterns:
            self.inverted[pattern.lower()].discard(atom_id)
        for key, value in atom.relations.items():
            self.relation_index[f"{key}:{value}"].discard(atom_id)
        for tag in atom.tags:
            self.concepts[tag].discard(atom_id)
        return atom

    def find_by_tokens(self, tokens: list[str], top_k: int = 10) -> list[tuple[Atom, float]]:
        candidate_ids: dict[str, float] = defaultdict(float)
        token_set = set(t.lower() for t in tokens)
        for token in token_set:
            for atom_id in self.inverted.get(token, set()):
                candidate_ids[atom_id] += 1.0
        trie_ids = self.trie.search_all_prefixes([t.lower() for t in tokens])
        for atom_id in trie_ids:
            candidate_ids[atom_id] += 0.5
        scored: list[tuple[Atom, float]] = []
        for atom_id, raw_score in candidate_ids.items():
            atom = self.atoms.get(atom_id)
            if atom is None:
                continue
            pattern_set = set(p.lower() for p in atom.patterns)
            if not pattern_set:
                continue
            overlap = len(token_set & pattern_set)
            coverage = overlap / len(pattern_set)
            idf = math.log(1 + len(self.atoms) / max(1, len(pattern_set)))
            score = (raw_score * 0.3 + coverage * 0.4 + atom.confidence * 0.2 + idf * 0.1)
            scored.append((atom, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def find_by_relation(self, key: str, value: str) -> list[Atom]:
        ids = self.relation_index.get(f"{key}:{value}", set())
        return [self.atoms[aid] for aid in ids if aid in self.atoms]

    def find_by_concept(self, concept: str) -> list[Atom]:
        ids = self.concepts.get(concept, set())
        return [self.atoms[aid] for aid in ids if aid in self.atoms]

    def find_chain(self, start_token: str, max_hops: int = 3) -> list[list[Atom]]:
        chains: list[list[Atom]] = []
        start_atoms = list(self.inverted.get(start_token.lower(), set()))
        if not start_atoms:
            return chains
        visited: set[str] = set()
        for start_id in start_atoms[:5]:
            atom = self.atoms.get(start_id)
            if atom is None:
                continue
            chain = [atom]
            visited.add(start_id)
            self._extend_chain(chain, visited, max_hops - 1, chains)
            visited.discard(start_id)
        chains.sort(key=len, reverse=True)
        return chains[:5]

    def _extend_chain(
        self,
        chain: list[Atom],
        visited: set[str],
        remaining: int,
        results: list[list[Atom]],
    ) -> None:
        if remaining <= 0 or len(chain) >= 4:
            if len(chain) >= 2:
                results.append(list(chain))
            return
        current = chain[-1]
        link_tokens: set[str] = set()
        for val in current.relations.values():
            for token in val.lower().split():
                if len(token) > 2 and token not in _STOP_WORDS:
                    link_tokens.add(token)
        for pattern in current.patterns[-3:]:
            if pattern.lower() not in _STOP_WORDS:
                link_tokens.add(pattern.lower())
        next_ids: set[str] = set()
        for token in link_tokens:
            next_ids.update(self.inverted.get(token, set()))
        next_ids -= visited
        scored: list[tuple[str, float]] = []
        for nid in next_ids:
            next_atom = self.atoms.get(nid)
            if next_atom is None or next_atom.level < 3:
                continue
            overlap = len(link_tokens & set(p.lower() for p in next_atom.patterns))
            if overlap > 0:
                scored.append((nid, overlap * next_atom.confidence))
        scored.sort(key=lambda x: x[1], reverse=True)
        for nid, _ in scored[:3]:
            next_atom = self.atoms[nid]
            chain.append(next_atom)
            visited.add(nid)
            self._extend_chain(chain, visited, remaining - 1, results)
            chain.pop()
            visited.discard(nid)
        if len(chain) >= 2:
            results.append(list(chain))

    @property
    def size(self) -> int:
        return len(self.atoms)

    def save(self, path: Path) -> None:
        data = {
            "version": "noesis-1.0",
            "timestamp": time.time(),
            "atom_count": len(self.atoms),
            "atoms": [a.to_dict() for a in self.atoms.values()],
        }
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

    def load(self, path: Path) -> int:
        data = json.loads(path.read_text(encoding="utf-8"))
        count = 0
        for ad in data.get("atoms", []):
            atom = Atom.from_dict(ad)
            self.add(atom)
            count += 1
        return count


def _atom_id(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def _tokenize(text: str) -> list[str]:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s\u0370-\u03FF\u0400-\u04FF]", " ", text)
    return [t for t in text.split() if len(t) > 1]


_STOP_WORDS: set[str] = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "to", "of", "in", "for",
    "on", "with", "at", "by", "from", "as", "into", "through", "during",
    "before", "after", "above", "below", "between", "under", "again",
    "further", "then", "once", "here", "there", "when", "where", "why",
    "how", "all", "each", "every", "both", "few", "more", "most", "other",
    "some", "such", "no", "nor", "not", "only", "own", "same", "so",
    "than", "too", "very", "just", "because", "but", "and", "or", "if",
    "while", "about", "up", "out", "off", "over", "also", "it", "its",
    "this", "that", "these", "those", "i", "me", "my", "we", "our",
    "you", "your", "he", "him", "his", "she", "her", "they", "them",
    "what", "which", "who", "whom", "whose",
    "το", "ο", "η", "τα", "οι", "ένα", "μια", "και", "ή", "αλλά",
    "σε", "από", "για", "με", "ως", "στο", "στη", "στον", "στην",
    "του", "της", "των", "τον", "την", "είναι", "ήταν", "θα", "να",
    "που", "αυτό", "αυτή", "αυτός", "δεν", "μην",
}


def _remove_stopwords(tokens: list[str]) -> list[str]:
    return [t for t in tokens if t not in _STOP_WORDS]


def _ngrams(tokens: list[str], n: int) -> list[list[str]]:
    if len(tokens) < n:
        return [tokens] if tokens else []
    return [tokens[i:i + n] for i in range(len(tokens) - n + 1)]


class Compressor:
    def __init__(self, min_pattern_len: int = 2, max_pattern_len: int = 5) -> None:
        self.min_pattern_len = min_pattern_len
        self.max_pattern_len = max_pattern_len
        self._pattern_freq: dict[str, int] = defaultdict(int)

    def compress(self, text: str) -> list[Atom]:
        text = self._strip_markdown(text)
        sentences = self._split_sentences(text)
        atoms: list[Atom] = []
        for sentence in sentences:
            atoms.extend(self._compress_sentence(sentence))
        return atoms

    def _strip_markdown(self, text: str) -> str:
        text = re.sub(r'```[\s\S]*?```', '', text)
        text = re.sub(r'`[^`]+`', '', text)
        text = re.sub(r'^\|.*\|$', '', text, flags=re.MULTILINE)
        text = re.sub(r'^[-|:]+$', '', text, flags=re.MULTILINE)
        text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
        text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
        text = re.sub(r'\*([^*]+)\*', r'\1', text)
        text = re.sub(r'^\s*[-*]\s+\[.\]\s*', '', text, flags=re.MULTILINE)
        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
        text = re.sub(r'[═─│├└┌┐╔╚║╗╝╠╣╬]+', '', text)
        text = re.sub(r'^\s*[-*>]\s+', '', text, flags=re.MULTILINE)
        return text

    def _split_sentences(self, text: str) -> list[str]:
        lines = text.split("\n")
        raw_sentences: list[str] = []
        for line in lines:
            line = line.strip()
            if not line or len(line) < 30:
                continue
            if self._is_code_or_markup(line):
                continue
            parts = re.split(r'(?<=[.!?])\s+', line)
            for part in parts:
                part = part.strip()
                if len(part) >= 30 and self._is_natural_language(part):
                    raw_sentences.append(part)
        return raw_sentences

    def _is_natural_language(self, text: str) -> bool:
        line = text.strip()
        words = line.split()
        if len(words) < 5:
            return False
        alpha_words = sum(1 for w in words if w[0].isalpha() or w[0] in "ΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩαβγδεζηθικλμνξοπρστυφχψωάέήίόύώ")
        if alpha_words / len(words) < 0.7:
            return False
        special = sum(1 for c in line if c in "{}[]()=<>|&;$@#`\\_*~^→←├└│─═")
        if len(line) > 0 and special / len(line) > 0.05:
            return False
        if re.search(r'\s{3,}', line):
            return False
        if line.startswith(("-", "*", ">", "#", "|")):
            return False
        return True

    def _is_code_or_markup(self, text: str) -> bool:
        line = text.strip()
        if line.startswith(("```", "│", "├", "└", "═", "─", "┌", "┐", "╔", "╚", "║")):
            return True
        if line.startswith(("import ", "from ", "def ", "class ", "async ", "await ", "self.")):
            return True
        if line.startswith(("$", ">>>", "root@", "nous:", "//", "/*", "#!", "% ", "pip ")):
            return True
        if line.startswith("|") and "|" in line[1:]:
            return True
        if line.startswith(("- ", "* ", "> ", "# ")):
            return True
        if line.startswith("**") and ":**" in line:
            return True
        if "`" in line:
            return True
        if "--" in line and re.search(r'--\w', line):
            return True
        code_chars = sum(1 for c in line if c in "{}[]()=<>|&;$@#`\\_")
        if len(line) > 0 and code_chars / len(line) > 0.08:
            return True
        if re.match(r'^[A-Z_]{2,}\s*[:=]', line):
            return True
        return False

    def _compress_sentence(self, sentence: str) -> list[Atom]:
        tokens = _tokenize(sentence)
        keywords = _remove_stopwords(tokens)
        if not keywords:
            return []
        atoms: list[Atom] = []
        sentence_atom = Atom(
            id=_atom_id(sentence),
            patterns=keywords[:8],
            relations=self._extract_relations(tokens),
            template=sentence,
            level=3,
            confidence=0.8,
            source="compression",
            tags=self._extract_tags(keywords),
        )
        atoms.append(sentence_atom)
        return atoms

    def _extract_relations(self, tokens: list[str]) -> dict[str, str]:
        relations: dict[str, str] = {}
        keywords = _remove_stopwords(tokens)
        if len(keywords) >= 2:
            relations["subject"] = keywords[0]
            relations["context"] = keywords[-1]
        if len(keywords) >= 3:
            relations["predicate"] = keywords[1]
            relations["object"] = keywords[2]
        for i, token in enumerate(tokens):
            if token in ("is", "are", "was", "were", "είναι", "ήταν"):
                if i > 0 and i < len(tokens) - 1:
                    subj = " ".join(_remove_stopwords(tokens[:i]))
                    obj = " ".join(_remove_stopwords(tokens[i + 1:]))
                    if subj and obj:
                        relations["subject"] = subj
                        relations["is_a"] = obj
                        break
        return relations

    def _extract_tags(self, keywords: list[str]) -> set[str]:
        tags: set[str] = set()
        for kw in keywords[:5]:
            if len(kw) > 3:
                tags.add(kw)
        return tags


class Resonator:
    def __init__(self, diversity_penalty: float = 0.3) -> None:
        self.diversity_penalty = diversity_penalty

    def resonate(
        self,
        query: str,
        lattice: Lattice,
        top_k: int = 10,
        min_score: float = 0.05,
    ) -> list[tuple[Atom, float]]:
        tokens = _tokenize(query)
        keywords = _remove_stopwords(tokens)
        if not keywords:
            keywords = tokens
        if not keywords:
            return []
        candidates = lattice.find_by_tokens(keywords, top_k=top_k * 3)
        query_set = set(keywords)
        rescored: list[tuple[Atom, float]] = []
        for atom, base_score in candidates:
            relevance = self._relevance_score(atom, query_set)
            recency = self._recency_score(atom)
            usage_score = min(1.0, math.log1p(atom.usage_count) / 5.0)
            level_bonus = 0.3 if atom.level >= 3 else -0.2
            template_quality = 0.1 if len(atom.template) > 30 else -0.1
            total = (
                base_score * 0.25
                + relevance * 0.3
                + atom.confidence * 0.1
                + recency * 0.05
                + usage_score * 0.05
                + level_bonus
                + template_quality
            )
            if total >= min_score:
                rescored.append((atom, total))
        rescored.sort(key=lambda x: x[1], reverse=True)
        diversified = self._diversify(rescored, top_k)
        return diversified

    def _relevance_score(self, atom: Atom, query_tokens: set[str]) -> float:
        if not atom.patterns:
            return 0.0
        pattern_set = set(p.lower() for p in atom.patterns)
        intersection = query_tokens & pattern_set
        if not intersection:
            return 0.0
        precision = len(intersection) / len(query_tokens) if query_tokens else 0
        recall = len(intersection) / len(pattern_set)
        if precision + recall == 0:
            return 0.0
        return 2 * (precision * recall) / (precision + recall)

    def _recency_score(self, atom: Atom) -> float:
        age_hours = (time.time() - atom.birth) / 3600
        return 1.0 / (1.0 + math.log1p(age_hours / 24))

    def _diversify(
        self,
        scored: list[tuple[Atom, float]],
        top_k: int,
    ) -> list[tuple[Atom, float]]:
        if len(scored) <= top_k:
            return scored
        selected: list[tuple[Atom, float]] = []
        seen_patterns: set[str] = set()
        for atom, score in scored:
            pattern_key = frozenset(atom.patterns[:3])
            overlap = len(set(atom.patterns) & seen_patterns)
            penalty = overlap * self.diversity_penalty
            adjusted = max(0.0, score - penalty)
            selected.append((atom, adjusted))
            seen_patterns.update(atom.patterns)
        selected.sort(key=lambda x: x[1], reverse=True)
        return selected[:top_k]


class Weaver:
    def __init__(self) -> None:
        self._connectors: list[str] = [
            ". ", "; ", " — ", ". Furthermore, ", ". Additionally, ",
            ". Also, ", ". In particular, ",
        ]

    def weave(
        self,
        resonated: list[tuple[Atom, float]],
        query: str,
        max_atoms: int = 5,
        mode: str = "compose",
    ) -> str:
        if not resonated:
            return ""
        top = resonated[:max_atoms]
        if mode == "direct" and top:
            best_atom, _ = top[0]
            best_atom.usage_count += 1
            return best_atom.template
        if mode == "compose":
            return self._compose(top, query)
        if mode == "reason":
            return self._reason_chain(top, query)
        return self._compose(top, query)

    def _compose(self, atoms: list[tuple[Atom, float]], query: str) -> str:
        if not atoms:
            return ""
        sentence_atoms = [(a, s) for a, s in atoms if a.level >= 3]
        if not sentence_atoms:
            sentence_atoms = atoms
        fragments: list[str] = []
        seen_content: set[str] = set()
        for atom, score in sentence_atoms:
            atom.usage_count += 1
            template = atom.template.strip()
            if not template or len(template) < 10:
                continue
            content_key = template[:50].lower()
            if content_key in seen_content:
                continue
            seen_content.add(content_key)
            if not template[-1] in ".!?":
                template += "."
            fragments.append(template)
        if not fragments:
            return ""
        if len(fragments) == 1:
            return fragments[0]
        return " ".join(fragments)

    def _reason_chain(self, atoms: list[tuple[Atom, float]], query: str) -> str:
        if not atoms:
            return ""
        lines: list[str] = []
        for i, (atom, score) in enumerate(atoms):
            atom.usage_count += 1
            if atom.relations:
                subj = atom.relations.get("subject", "")
                is_a = atom.relations.get("is_a", "")
                pred = atom.relations.get("predicate", "")
                obj = atom.relations.get("object", atom.relations.get("context", ""))
                if is_a:
                    lines.append(f"{subj} ≡ {is_a}")
                elif subj and pred:
                    lines.append(f"{subj} → {pred} → {obj}" if obj else f"{subj} → {pred}")
                else:
                    lines.append(atom.template)
            else:
                lines.append(atom.template)
        return " ∴ ".join(lines)

    def weave_chain(self, chains: list[list["Atom"]], query: str) -> str:
        if not chains:
            return ""
        best_chain = chains[0]
        parts: list[str] = []
        for i, atom in enumerate(best_chain):
            atom.usage_count += 1
            template = atom.template.strip()
            if not template or len(template) < 10:
                continue
            if not template[-1] in ".!?":
                template += "."
            parts.append(template)
        if not parts:
            return ""
        return " → ".join(parts) if len(parts) <= 3 else " ".join(parts)

    def _pick_connector(self, prev: str, curr: str) -> str:
        if prev.endswith((".", "!", "?")):
            return " "
        return ". "


class OracleBridge:
    def __init__(
        self,
        call_fn: Optional[Callable[[str], str]] = None,
        confidence_threshold: float = 0.3,
    ) -> None:
        self.call_fn = call_fn
        self.confidence_threshold = confidence_threshold
        self.call_count: int = 0
        self.learn_count: int = 0

    def should_consult(self, resonated: list[tuple[Atom, float]]) -> bool:
        if not resonated:
            return True
        best_score = resonated[0][1] if resonated else 0.0
        return best_score < self.confidence_threshold

    def consult(self, query: str) -> Optional[str]:
        if self.call_fn is None:
            return None
        self.call_count += 1
        try:
            return self.call_fn(query)
        except Exception:
            return None


class NoesisEngine:
    def __init__(
        self,
        oracle_fn: Optional[Callable[[str], str]] = None,
        oracle_threshold: float = 0.3,
    ) -> None:
        self.lattice = Lattice()
        self.compressor = Compressor()
        self.resonator = Resonator()
        self.weaver = Weaver()
        self.oracle = OracleBridge(
            call_fn=oracle_fn,
            confidence_threshold=oracle_threshold,
        )
        self._query_log: list[dict[str, Any]] = []
        self._oracle_queries: int = 0
        self._lattice_queries: int = 0

    def learn(self, text: str, source: str = "input") -> int:
        atoms = self.compressor.compress(text)
        added = 0
        for atom in atoms:
            atom.source = source
            if atom.id not in self.lattice.atoms:
                self.lattice.add(atom)
                added += 1
            else:
                existing = self.lattice.atoms[atom.id]
                existing.confidence = min(1.0, existing.confidence + 0.05)
                existing.usage_count += 1
        return added

    def learn_file(self, path: Path) -> int:
        text = path.read_text(encoding="utf-8")
        return self.learn(text, source=str(path))

    def think(
        self,
        query: str,
        mode: str = "compose",
        top_k: int = 5,
        use_oracle: bool = True,
    ) -> ThinkResult:
        t0 = time.perf_counter()
        resonated = self.resonator.resonate(query, self.lattice, top_k=top_k)
        oracle_used = False
        oracle_response: Optional[str] = None
        if use_oracle and self.oracle.should_consult(resonated):
            oracle_response = self.oracle.consult(query)
            if oracle_response:
                oracle_used = True
                self._oracle_queries += 1
                new_atoms = self.learn(oracle_response, source="oracle")
                resonated = self.resonator.resonate(query, self.lattice, top_k=top_k)
        if not oracle_used:
            self._lattice_queries += 1
        if mode == "chain":
            tokens = _tokenize(query)
            keywords = _remove_stopwords(tokens)
            chains: list[list[Atom]] = []
            for kw in keywords[:3]:
                chains.extend(self.lattice.find_chain(kw, max_hops=3))
            if chains:
                response = self.weaver.weave_chain(chains, query)
            else:
                response = self.weaver.weave(resonated, query, mode="compose")
        else:
            response = self.weaver.weave(resonated, query, mode=mode)
        if not response and oracle_response:
            response = oracle_response
        elapsed = time.perf_counter() - t0
        result = ThinkResult(
            query=query,
            response=response,
            atoms_matched=len(resonated),
            top_score=resonated[0][1] if resonated else 0.0,
            oracle_used=oracle_used,
            elapsed_ms=elapsed * 1000,
            atoms_in_lattice=self.lattice.size,
        )
        self._query_log.append(result.to_dict())
        return result

    def evolve(self, min_confidence: float = 0.1, min_usage: int = 0) -> EvolutionResult:
        initial_size = self.lattice.size
        pruned = 0
        merged = 0
        to_remove: list[str] = []
        for atom_id, atom in self.lattice.atoms.items():
            if atom.fitness < min_confidence and atom.usage_count <= min_usage:
                to_remove.append(atom_id)
        for atom_id in to_remove:
            self.lattice.remove(atom_id)
            pruned += 1
        pattern_groups: dict[str, list[str]] = defaultdict(list)
        for atom_id, atom in self.lattice.atoms.items():
            key = " ".join(sorted(atom.patterns[:3]))
            if key:
                pattern_groups[key].append(atom_id)
        for key, group_ids in pattern_groups.items():
            if len(group_ids) <= 1:
                continue
            group_atoms = [self.lattice.atoms[aid] for aid in group_ids if aid in self.lattice.atoms]
            if len(group_atoms) <= 1:
                continue
            best = max(group_atoms, key=lambda a: a.fitness)
            for atom in group_atoms:
                if atom.id != best.id:
                    best.confidence = min(1.0, best.confidence + atom.confidence * 0.1)
                    best.usage_count += atom.usage_count
                    best.success_count += atom.success_count
                    self.lattice.remove(atom.id)
                    merged += 1
        return EvolutionResult(
            initial_size=initial_size,
            final_size=self.lattice.size,
            pruned=pruned,
            merged=merged,
        )

    def reinforce(self, query: str, was_helpful: bool) -> None:
        resonated = self.resonator.resonate(query, self.lattice, top_k=3)
        for atom, _ in resonated:
            if was_helpful:
                atom.success_count += 1
                atom.confidence = min(1.0, atom.confidence + 0.02)
            else:
                atom.confidence = max(0.0, atom.confidence - 0.05)

    def save(self, path: Path) -> None:
        self.lattice.save(path)

    def load(self, path: Path) -> int:
        return self.lattice.load(path)

    def stats(self) -> dict[str, Any]:
        if not self.lattice.atoms:
            return {
                "atoms": 0, "queries": len(self._query_log),
                "oracle_calls": self.oracle.call_count,
                "avg_confidence": 0.0, "avg_fitness": 0.0,
                "autonomy": "N/A",
            }
        confidences = [a.confidence for a in self.lattice.atoms.values()]
        fitnesses = [a.fitness for a in self.lattice.atoms.values()]
        levels = defaultdict(int)
        sources = defaultdict(int)
        for a in self.lattice.atoms.values():
            levels[a.level] += 1
            sources[a.source] += 1
        total_answered = self._oracle_queries + self._lattice_queries
        if total_answered > 0:
            autonomy_pct = (self._lattice_queries / total_answered) * 100
            autonomy_str = f"{autonomy_pct:.1f}%"
        else:
            autonomy_str = "N/A"
        return {
            "atoms": self.lattice.size,
            "queries": len(self._query_log),
            "oracle_calls": self.oracle.call_count,
            "lattice_answers": self._lattice_queries,
            "oracle_answers": self._oracle_queries,
            "autonomy": autonomy_str,
            "avg_confidence": sum(confidences) / len(confidences),
            "max_confidence": max(confidences),
            "avg_fitness": sum(fitnesses) / len(fitnesses),
            "by_level": dict(levels),
            "by_source": dict(sources),
            "unique_patterns": len(self.lattice.inverted),
            "unique_concepts": len(self.lattice.concepts),
            "unique_relations": len(self.lattice.relation_index),
        }

    def inspect(self, atom_id: str) -> Optional[dict[str, Any]]:
        atom = self.lattice.atoms.get(atom_id)
        if atom is None:
            return None
        return atom.to_dict()

    def search_atoms(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        resonated = self.resonator.resonate(query, self.lattice, top_k=top_k)
        return [
            {"atom": atom.to_dict(), "score": round(score, 4)}
            for atom, score in resonated
        ]


@dataclass
class ThinkResult:
    query: str
    response: str
    atoms_matched: int
    top_score: float
    oracle_used: bool
    elapsed_ms: float
    atoms_in_lattice: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "response": self.response[:200],
            "atoms_matched": self.atoms_matched,
            "top_score": round(self.top_score, 4),
            "oracle_used": self.oracle_used,
            "elapsed_ms": round(self.elapsed_ms, 2),
        }

    def __str__(self) -> str:
        oracle_tag = " [oracle]" if self.oracle_used else ""
        return (
            f"═══ Νόηση{oracle_tag} ═══\n"
            f"{self.response}\n"
            f"───\n"
            f"atoms: {self.atoms_matched} | "
            f"score: {self.top_score:.3f} | "
            f"time: {self.elapsed_ms:.1f}ms | "
            f"lattice: {self.atoms_in_lattice}"
        )


@dataclass
class EvolutionResult:
    initial_size: int
    final_size: int
    pruned: int
    merged: int

    def __str__(self) -> str:
        return (
            f"═══ Noesis Evolution ═══\n"
            f"Before: {self.initial_size} atoms\n"
            f"Pruned: {self.pruned} | Merged: {self.merged}\n"
            f"After:  {self.final_size} atoms\n"
            f"Compression ratio: {self.final_size / max(1, self.initial_size):.2%}"
        )


class NoesisSoul:
    """
    NOUS integration: wraps NoesisEngine as a Soul that can be used
    in a NOUS world. Implements the sense/speak/listen protocol.
    """

    def __init__(
        self,
        name: str = "Noesis",
        engine: Optional[NoesisEngine] = None,
        lattice_path: Optional[Path] = None,
    ) -> None:
        self.name = name
        self.engine = engine or NoesisEngine()
        self.lattice_path = lattice_path
        if lattice_path and lattice_path.exists():
            self.engine.load(lattice_path)

    def sense_learn(self, text: str, source: str = "input") -> dict[str, Any]:
        added = self.engine.learn(text, source=source)
        return {
            "atoms_added": added,
            "lattice_size": self.engine.lattice.size,
        }

    def sense_think(
        self,
        query: str,
        mode: str = "compose",
        top_k: int = 5,
    ) -> dict[str, Any]:
        result = self.engine.think(query, mode=mode, top_k=top_k)
        return {
            "response": result.response,
            "atoms_matched": result.atoms_matched,
            "score": round(result.top_score, 4),
            "oracle_used": result.oracle_used,
            "elapsed_ms": round(result.elapsed_ms, 2),
        }

    def sense_evolve(self) -> dict[str, Any]:
        result = self.engine.evolve()
        return {
            "pruned": result.pruned,
            "merged": result.merged,
            "before": result.initial_size,
            "after": result.final_size,
        }

    def sense_stats(self) -> dict[str, Any]:
        return self.engine.stats()

    def sense_save(self) -> dict[str, Any]:
        if self.lattice_path:
            self.engine.save(self.lattice_path)
            return {"saved": True, "path": str(self.lattice_path)}
        return {"saved": False, "reason": "no lattice_path configured"}

    def sense_inspect(self, atom_id: str) -> dict[str, Any]:
        result = self.engine.inspect(atom_id)
        if result is None:
            return {"error": f"Atom {atom_id} not found"}
        return result

    def sense_search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        return self.engine.search_atoms(query, top_k=top_k)

import noesis_quality_patch

import noesis_quality_patch
import noesis_quality_patch
import noesis_reasoning_patch
import noesis_scaling_patch
import noesis_scaling_patch
import noesis_autofeeding_patch
import noesis_sources_patch      # Phase 7
import noesis_hardening_patch    # Phase 8
import noesis_superbrain

# --- Weaning auto-init ---
def _init_weaning_on_load(engine):
    """Initialize weaner after lattice is loaded."""
    original_load = engine.load
    def patched_load(*args, **kwargs):
        result = original_load(*args, **kwargs)
        if hasattr(engine, 'weaner') and engine.weaner is not None:
            try:
                atom_count = len(engine.lattice.atoms) if hasattr(engine.lattice, 'atoms') else 0
                engine.weaner.update_stats(atom_count)
                engine.weaner.initialized = True
            except Exception:
                pass
        elif hasattr(engine, 'init_autofeeding'):
            try:
                engine.init_autofeeding()
            except Exception:
                pass
        return result
    engine.load = patched_load

try:
    from noesis_engine import NoesisEngine as _WeanEngine
    for _inst_name in list(vars().keys()):
        _inst = vars().get(_inst_name)
        if isinstance(_inst, _WeanEngine):
            _init_weaning_on_load(_inst)
except Exception:
    pass
         # Superbrain bridge
import noesis_embeddings_patch
import noesis_domain_patch
import noesis_domain_oracle_patch
