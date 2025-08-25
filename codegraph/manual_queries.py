from __future__ import annotations
from typing import Set
from .graph_schema import CodeGraph, NodeType, EdgeType

CONTROLLER_ANNOS = {"@Controller", "@RestController"}
REQUEST_ANNOS = {"@RequestMapping", "@GetMapping", "@PostMapping", "@PutMapping", "@PatchMapping", "@DeleteMapping"}
LISTENER_ANNOS = {"@EventListener", "@KafkaListener", "@RabbitListener", "@JmsListener"}
LISTENER_INTERFACES = {"ApplicationListener", "MessageListener"}


def slice_controllers(G: CodeGraph, neighbors: int = 1) -> CodeGraph:
    seeds: Set[str] = set()
    for n, d in G.g.nodes(data=True):
        if d.get("type") == NodeType.CLASS and any(a in CONTROLLER_ANNOS for a in d.get("annotations", [])):
            seeds.add(n)
    for n, d in G.g.nodes(data=True):
        if d.get("type") == NodeType.METHOD and any(a in REQUEST_ANNOS for a in d.get("annotations", [])):
            seeds.add(n)
    if not seeds:
        return G.subgraph_by_nodes(set())
    return G.neighbors_k_hops(seeds, k=neighbors)


def slice_listeners(G: CodeGraph, neighbors: int = 1) -> CodeGraph:
    seeds: Set[str] = set()
    for n, d in G.g.nodes(data=True):
        if d.get("type") == NodeType.CLASS and any(a in LISTENER_ANNOS for a in d.get("annotations", [])):
            seeds.add(n)
    for u, v, data in G.g.edges(data=True):
        if data.get("type") == EdgeType.IMPLEMENTS:
            iface = G.g.nodes.get(v, {}).get("name") or ""
            if any(iface.endswith(LI) for LI in LISTENER_INTERFACES) or any(str(v).endswith(LI) for LI in LISTENER_INTERFACES):
                seeds.add(u)
    for n, d in G.g.nodes(data=True):
        if d.get("type") == NodeType.METHOD and any(a in LISTENER_ANNOS for a in d.get("annotations", [])):
            seeds.add(n)
    if not seeds:
        return G.subgraph_by_nodes(set())
    return G.neighbors_k_hops(seeds, k=neighbors)