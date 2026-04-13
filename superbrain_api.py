import sys
import time
import re
sys.path.insert(0, "/home/ubuntu/superbrain-env/lib/python3.10/site-packages")
sys.path.insert(0, "/home/ubuntu/superbrain")

from fastapi import FastAPI
from pydantic import BaseModel
import chromadb
from chromadb.utils import embedding_functions
from rank_bm25 import BM25Okapi

app = FastAPI(title="Superbrain API", version="1.1.0")
SUPERBRAIN_DB = "/home/ubuntu/superbrain/db"


def tokenize(text):
    return re.findall(r"[\w\u0370-\u03ff]+", text.lower())


def rrf(rankings, k=60):
    scores = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking):
            scores[doc_id] = scores.get(doc_id, 0) + 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


print("Loading Superbrain into memory...")
t0 = time.time()
_client = chromadb.PersistentClient(path=SUPERBRAIN_DB)
_ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-mpnet-base-v2")
_col = _client.get_collection(name="superbrain_knowledge_v2", embedding_function=_ef)
_all_data = _col.get(include=["documents", "metadatas"])
_all_ids = _all_data["ids"]
_all_docs = _all_data["documents"]
_all_metas = _all_data["metadatas"]
_tokenized_corpus = [tokenize(doc) for doc in _all_docs]
_bm25 = BM25Okapi(_tokenized_corpus)
_id_to_meta = {id_: meta for id_, meta in zip(_all_ids, _all_metas)}
_id_to_doc = {id_: doc for id_, doc in zip(_all_ids, _all_docs)}
print(f"Loaded {len(_all_ids)} chunks in {time.time()-t0:.1f}s")


class SearchRequest(BaseModel):
    query: str
    n_results: int = 3
    expand: bool = True


@app.get("/health")
def health():
    return {"status": "ok", "chunks": len(_all_ids), "version": "1.1.0"}


@app.post("/search")
def search(req: SearchRequest):
    t0 = time.time()
    try:
        query = req.query
        if req.expand:
            try:
                from query_expander import expand_query
                query = expand_query(query)
            except Exception:
                pass

        dense = _col.query(query_texts=[query], n_results=min(20, len(_all_ids)))
        dense_ids = dense["ids"][0]
        dense_distances = {id_: dist for id_, dist in zip(dense["ids"][0], dense["distances"][0])}

        query_tokens = tokenize(query)
        bm25_scores = _bm25.get_scores(query_tokens)
        bm25_ranking = [_all_ids[i] for i in sorted(range(len(bm25_scores)), key=lambda x: bm25_scores[x], reverse=True)[:20]]

        fused = rrf([dense_ids, bm25_ranking, bm25_ranking])

        results = []
        seen_titles = set()
        for doc_id, rrf_score in fused:
            meta = _id_to_meta.get(doc_id, {})
            title = meta.get("title", "")
            if title in seen_titles:
                continue
            seen_titles.add(title)
            results.append({
                "rank": len(results) + 1,
                "title": title,
                "domain": meta.get("domain", ""),
                "chunk_index": meta.get("chunk_index", 0),
                "key_concepts": meta.get("key_concepts", ""),
                "content": _id_to_doc.get(doc_id, ""),
                "rrf_score": round(rrf_score, 6),
                "semantic_distance": round(dense_distances.get(doc_id, 1.0), 4),
            })
            if len(results) >= req.n_results:
                break

        latency_ms = round((time.time() - t0) * 1000, 1)
        return {
            "query": req.query,
            "relevant_domains": results,
            "context": "\n\n".join([f'[{d["title"]}]\n{d["content"]}' for d in results]),
            "latency_ms": latency_ms,
        }
    except Exception as e:
        return {"error": str(e), "latency_ms": round((time.time() - t0) * 1000, 1)}


@app.get("/domains")
def domains():
    domain_map = {}
    for m in _all_metas:
        d = m.get("domain", "unknown")
        if d not in domain_map:
            domain_map[d] = 0
        domain_map[d] += 1
    return {"total": len(_all_ids), "domain_count": len(domain_map), "domains": domain_map}


@app.post("/reload")
def reload():
    global _all_data, _all_ids, _all_docs, _all_metas, _tokenized_corpus, _bm25, _id_to_meta, _id_to_doc
    _all_data = _col.get(include=["documents", "metadatas"])
    _all_ids = _all_data["ids"]
    _all_docs = _all_data["documents"]
    _all_metas = _all_data["metadatas"]
    _tokenized_corpus = [tokenize(doc) for doc in _all_docs]
    _bm25 = BM25Okapi(_tokenized_corpus)
    _id_to_meta = {id_: meta for id_, meta in zip(_all_ids, _all_metas)}
    _id_to_doc = {id_: doc for id_, doc in zip(_all_ids, _all_docs)}
    return {"status": "reloaded", "chunks": len(_all_ids)}
