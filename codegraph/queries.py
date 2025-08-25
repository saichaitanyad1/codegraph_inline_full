
from __future__ import annotations
from typing import List
from .graph_schema import CodeGraph, NodeType, EdgeType

CONTROLLER_ANNOS = {"@RestController", "@Controller", "@GetMapping", "@PostMapping", "@PutMapping", "@DeleteMapping", "@RequestMapping"}
LISTENER_ANNOS = {"@KafkaListener", "@RabbitListener", "@JmsListener", "@EventListener"}

def _with_neighbors(G: CodeGraph, ids: List[str], k: int) -> CodeGraph:
    return G.neighbors_k_hops(ids, k=k) if k > 0 else G.subgraph_by_nodes(ids)

def slice_controllers(G: CodeGraph, neighbors: int = 1) -> CodeGraph:
    seeds = []
    for nid, d in G.g.nodes(data=True):
        ann = set(d.get("annotations", []) or [])
        if ann & CONTROLLER_ANNOS:
            seeds.append(nid)
        # Classes annotated as controller
        if d.get("type") in (NodeType.CLASS, NodeType.METHOD) and any(a in CONTROLLER_ANNOS for a in ann):
            seeds.append(nid)
    return _with_neighbors(G, list(set(seeds)), neighbors)

def slice_listeners(G: CodeGraph, neighbors: int = 1) -> CodeGraph:
    seeds = []
    for nid, d in G.g.nodes(data=True):
        ann = set(d.get("annotations", []) or [])
        if ann & LISTENER_ANNOS:
            seeds.append(nid)
    # also classes implementing ApplicationListener* (java)
    for u, v, ed in G.g.edges(data=True):
        if ed.get("type") == EdgeType.IMPLEMENTS:
            if str(G.g.nodes.get(v, {}).get("fqn", "")).endswith("ApplicationListener") or str(G.g.nodes.get(v, {}).get("name", "")).endswith("ApplicationListener"):
                seeds.append(u)
    return _with_neighbors(G, list(set(seeds)), neighbors)
