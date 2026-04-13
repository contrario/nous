"""
Noesis ↔ Superbrain Bridge v2.0
============================
Connects Noesis lattice (BM25) with Superbrain ChromaDB (semantic search).
Hybrid search: query both systems, merge results, optionally learn into lattice.

v2.0: HTTP API via localhost:8900 (SSH tunnel to Oracle Server)
v1.0: Direct SSH (11s latency) → deprecated
"""
from __future__ import annotations
import asyncio, json, logging, os, time
from dataclasses import dataclass, field
from typing import Any, Optional
import httpx
logger = logging.getLogger("noesis.superbrain")
SUPERBRAIN_API = os.environ.get("SUPERBRAIN_API_URL", "http://localhost:8900")

@dataclass
class SuperbrainResult:
    query: str; chunks: list = field(default_factory=list); domains_hit: list = field(default_factory=list); latency_ms: float = 0.0; error: str | None = None

@dataclass
class HybridResult:
    query: str; noesis_response: str = ""; noesis_score: float = 0.0; noesis_atoms: int = 0; superbrain_chunks: list = field(default_factory=list); superbrain_domains: list = field(default_factory=list); merged_response: str = ""; source: str = ""; latency_ms: float = 0.0

class SuperbrainBridge:
    def __init__(self, engine=None, api_url=SUPERBRAIN_API, auto_learn=True, timeout=30.0):
        self.engine=engine; self.api_url=api_url.rstrip("/"); self.auto_learn=auto_learn; self.timeout=timeout
        self.calls=0; self.failures=0; self.atoms_learned=0
    async def _api_get(self, path):
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as c:
                return (await c.get(f"{self.api_url}{path}")).json()
        except Exception as e: return {"error":str(e)}
    async def _api_post(self, path, data):
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as c:
                return (await c.post(f"{self.api_url}{path}", json=data)).json()
        except Exception as e: return {"error":str(e)}
    async def search(self, query, n_results=5):
        self.calls+=1; t0=time.time()
        data=await self._api_post("/search",{"query":query,"n_results":n_results,"expand":True})
        latency=(time.time()-t0)*1000
        if "error" in data: self.failures+=1; return SuperbrainResult(query=query,error=data["error"],latency_ms=latency)
        chunks=data.get("relevant_domains",data.get("results",[]))
        domains=[]
        for c in chunks:
            if isinstance(c,dict):
                d=c.get("domain","")
                if d and d not in domains: domains.append(d)
        return SuperbrainResult(query=query,chunks=chunks,domains_hit=domains,latency_ms=latency)
    async def list_domains(self): return await self._api_get("/domains")
    async def health(self): return await self._api_get("/health")
    async def reload(self): return await self._api_post("/reload",{})
    async def hybrid_think(self,query,n_results=3,noesis_weight=0.5,superbrain_weight=0.5):
        t0=time.time(); nr=""; ns=0.0; na=0
        if self.engine:
            try:
                r=self.engine.think(query)
                if r: nr=getattr(r,"response",str(r)); ns=getattr(r,"top_score",0.0); na=len(getattr(r,"atoms",[]))
            except: pass
        sb=await self.search(query,n_results)
        sbt=[]
        for ck in sb.chunks:
            if isinstance(ck,dict):
                t=ck.get("content",ck.get("text",""))
                if t: sbt.append(str(t)[:500])
        mp=[]; src=""
        if ns>0.5 and sbt: mp.append(nr); mp.append("\n--- Superbrain ---"); mp.extend(sbt[:3]); src="hybrid"
        elif ns>0.5: mp.append(nr); src="noesis"
        elif sbt: mp.extend(sbt[:3]); src="superbrain"
        else: mp.append("No results."); src="none"
        if self.auto_learn and self.engine and sbt:
            ab=len(self.engine.lattice.atoms) if hasattr(self.engine,"lattice") else 0
            for t in sbt:
                try: self.engine.learn(t,source=f"superbrain:{sb.domains_hit[0] if sb.domains_hit else 'unknown'}")
                except: pass
            new=len(self.engine.lattice.atoms)-ab if hasattr(self.engine,"lattice") else 0
            self.atoms_learned+=new
        return HybridResult(query=query,noesis_response=nr,noesis_score=ns,noesis_atoms=na,superbrain_chunks=sb.chunks,superbrain_domains=sb.domains_hit,merged_response="\n".join(mp),source=src,latency_ms=(time.time()-t0)*1000)
    def stats(self): return {"calls":self.calls,"failures":self.failures,"atoms_learned":self.atoms_learned,"api_url":self.api_url,"auto_learn":self.auto_learn}

def install_superbrain_patch():
    try:
        from noesis_engine import NoesisEngine
    except ImportError: return
    _bridge=None
    def _get_bridge(engine):
        nonlocal _bridge
        if _bridge is None: _bridge=SuperbrainBridge(engine=engine)
        return _bridge
    def _run_async(coro):
        try:
            loop=asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as p: return p.submit(asyncio.run,coro).result()
            return loop.run_until_complete(coro)
        except RuntimeError: return asyncio.run(coro)
    def superbrain_search(self,query,n_results=3):
        r=_run_async(_get_bridge(self).search(query,n_results))
        if r.error: return {"error":r.error}
        return {"query":r.query,"chunks":r.chunks,"domains":r.domains_hit,"latency_ms":round(r.latency_ms,1)}
    def superbrain_think(self,query,n_results=3):
        r=_run_async(_get_bridge(self).hybrid_think(query,n_results))
        return {"query":r.query,"source":r.source,"noesis_score":round(r.noesis_score,3),"noesis_atoms":r.noesis_atoms,"superbrain_domains":r.superbrain_domains,"superbrain_chunks":len(r.superbrain_chunks),"merged_response":r.merged_response,"latency_ms":round(r.latency_ms,1)}
    def superbrain_domains(self): return _run_async(_get_bridge(self).list_domains())
    def superbrain_stats(self): return _get_bridge(self).stats()
    def superbrain_health(self): return _run_async(_get_bridge(self).health())
    NoesisEngine.superbrain_search=superbrain_search
    NoesisEngine.superbrain_think=superbrain_think
    NoesisEngine.superbrain_domains=superbrain_domains
    NoesisEngine.superbrain_stats=superbrain_stats
    NoesisEngine.superbrain_health=superbrain_health
    logger.info("Superbrain bridge patched (HTTP API)")

def _patch_telegram():
    try: import noesis_telegram
    except ImportError: return
    if not hasattr(noesis_telegram,"NoesisTelegramBot"): return
    B=noesis_telegram.NoesisTelegramBot; oi=B.__init__
    def pi(self,*a,**k):
        oi(self,*a,**k)
        if hasattr(self,"commands"): self.commands["superbrain"]=self._cmd_sb; self.commands["sb"]=self._cmd_sb; self.commands["domains"]=self._cmd_dom
    def _cmd_sb(self,cid,txt):
        if not txt.strip(): return "Usage: /superbrain <query>"
        try:
            r=self.engine.superbrain_think(txt.strip())
            if "error" in r: return f"Error: {r['error']}"
            return f"Hybrid: {txt.strip()[:50]}\nSource: {r['source']}\nScore: {r['noesis_score']}\nSB: {r['superbrain_chunks']} chunks {','.join(r['superbrain_domains'][:3])}\n{rr['latency_ms']}ms\n\n{r['merged_response'][:2000]}"
        except Exception as e: return f"Error: {e}"
    def _cmd_dom(self,cid,txt):
        try:
            r=self.engine.superbrain_domains()
            if "error" in r: return f"Error: {r['error']}"
            lines=[f"Domains: {r.get('domain_count','~')} | Chunks: {r.get('total','~')}"]
            for d,c in sorted(r.get("domains",{}).items(),key=lambda x:-x[1])[:20]: lines.append(f"  {d}: {c}")
            return "\n".join(lines)
        except Exception as e: return f"Error: {e}"
    B.__init__=pi; B._cmd_sb=_cmd_sb; B._cmd_dom=_cmd_dom

install_superbrain_patch()
_patch_telegram()
logger.info("Noesis Superbrain bridge active (HTTP API)")