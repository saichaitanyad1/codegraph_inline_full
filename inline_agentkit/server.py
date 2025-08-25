from __future__ import annotations
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
import os, tempfile, shutil
from subprocess import run

from .graph_builder import build_graph_from_repo
from .graph_schema import CodeGraph
from .queries import slice_controllers, slice_listeners
from .llm_packager import build_llm_pack
from .query_engine import dynamic_query

app = FastAPI(title="CodeGraph Toolkit API", version="0.3.0")

# Optional CORS for agent platforms
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GRAPH: Optional[CodeGraph] = None

class BuildReq(BaseModel):
    repo: str = Field(..., description="Path to source repo mounted in container")
    lang: str = Field("auto", description="auto|java|python")

class BuildFromGitReq(BaseModel):
    git_url: str
    branch: Optional[str] = None
    lang: str = "auto"

class QueryReq(BaseModel):
    query: Dict[str, Any] = Field(default_factory=dict)

class SliceReq(BaseModel):
    kind: str = Field(..., description="controllers|listeners")
    neighbors: int = 1

class PackReq(BaseModel):
    scenario: str = Field(..., description="controllers|listeners")
    out_dir: str = "./out/llm"

@app.post("/build")
def build(req: BuildReq):
    global GRAPH
    GRAPH = build_graph_from_repo(req.repo, lang=req.lang)
    return {"status": "ok", "nodes": GRAPH.g.number_of_nodes(), "edges": GRAPH.g.number_of_edges()}

@app.post("/build-from-git")
def build_from_git(req: BuildFromGitReq):
    tmp = tempfile.mkdtemp(prefix="cg_git_")
    try:
        cmd = ["git", "clone", "--depth", "1"]
        if req.branch:
            cmd += ["-b", req.branch]
        cmd += [req.git_url, tmp]
        r = run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            return {"error": "git clone failed", "stderr": r.stderr}
        global GRAPH
        GRAPH = build_graph_from_repo(tmp, lang=req.lang)
        return {"status": "ok", "nodes": GRAPH.g.number_of_nodes(), "edges": GRAPH.g.number_of_edges()}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

@app.post("/query")
def query(req: QueryReq):
    if GRAPH is None:
        return {"error": "graph not built; call /build first"}
    sg = dynamic_query(GRAPH, req.query)
    return sg.to_json()

@app.post("/slice")
def slice(req: SliceReq):
    if GRAPH is None:
        return {"error": "graph not built; call /build first"}
    if req.kind == "controllers":
        sg = slice_controllers(GRAPH, neighbors=req.neighbors)
    elif req.kind == "listeners":
        sg = slice_listeners(GRAPH, neighbors=req.neighbors)
    else:
        return {"error": "unknown slice kind"}
    return sg.to_json()

@app.post("/llm-pack")
def pack(req: PackReq):
    if GRAPH is None:
        return {"error": "graph not built; call /build first"}
    out = os.path.join(req.out_dir, req.scenario)
    build_llm_pack(GRAPH, req.scenario, out)
    return {"status": "ok", "out": out}