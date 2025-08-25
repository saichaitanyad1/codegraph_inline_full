from __future__ import annotations
from typing import List
from .graph_schema import CodeGraph, NodeType, EdgeType

CONTROLLER_ANNOS = {"@RestController", "@Controller", "@GetMapping", "@PostMapping", "@PutMapping", "@DeleteMapping", "@PatchMapping", "@RequestMapping"}
LISTENER_ANNOS   = {"@KafkaListener", "@RabbitListener", "@JmsListener", "@EventListener"}

def _has_any_controller_anno(d: dict) -> bool:
    http = (d.get("extras", {}) or {}).get("http") or {}
    if http.get("methods") or http.get("combined_paths"):
        return True
    names = set(d.get("annotations", []) or [])
    texts = set((d.get("extras", {}) or {}).get("annotation_texts", []) or [])
    return any(any(txt.startswith(tag) for txt in texts) or (tag in names) for tag in CONTROLLER_ANNOS)

def _has_any_listener_anno(d: dict) -> bool:
    names = set(d.get("annotations", []) or [])
    texts = set((d.get("extras", {}) or {}).get("annotation_texts", []) or [])
    return any(any(txt.startswith(tag) for txt in texts) or (tag in names) for tag in LISTENER_ANNOS)

def _with_neighbors(G: CodeGraph, ids: List[str], k: int) -> CodeGraph:
    return G.neighbors_k_hops(ids, k=k) if k > 0 else G.subgraph_by_nodes(ids)

def slice_controllers(G: CodeGraph, neighbors: int = 1) -> CodeGraph:
    seeds = []
    for nid, d in G.g.nodes(data=True):
        if d.get("type") in (NodeType.CLASS, NodeType.METHOD) and _has_any_controller_anno(d):
            seeds.append(nid)
    return _with_neighbors(G, list(set(seeds)), neighbors)

def slice_listeners(G: CodeGraph, neighbors: int = 1) -> CodeGraph:
    seeds = []
    for nid, d in G.g.nodes(data=True):
        if d.get("type") in (NodeType.CLASS, NodeType.METHOD) and _has_any_listener_anno(d):
            seeds.append(nid)
    for u, v, ed in G.g.edges(data=True):
        if ed.get("type") == EdgeType.IMPLEMENTS:
            if str(G.g.nodes.get(v, {}).get("fqn", "")).endswith("ApplicationListener") or str(G.g.nodes.get(v, {}).get("name", "")).endswith("ApplicationListener"):
                seeds.append(u)
    return _with_neighbors(G, list(set(seeds)), neighbors)
