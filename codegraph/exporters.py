
from __future__ import annotations
from typing import Iterable
from .graph_schema import CodeGraph

def compact_for_llm(G: CodeGraph, token_budget_nodes: int = 400) -> CodeGraph:
    # naive compaction: limit number of nodes
    nodes = list(G.g.nodes())[:token_budget_nodes]
    return G.subgraph_by_nodes(nodes)

def export_json(G: CodeGraph, path: str):
    G.export_json(path)


def export_graphml(G: CodeGraph, path: str):
    G.export_graphml(path)


def export_mermaid(G: CodeGraph, path: str, node_limit: int = 200):
    G.export_mermaid(path, node_limit=node_limit)


# def compact_for_llm(
#     G: CodeGraph,
#     token_budget_nodes: int = 400,
#     include_edges: Iterable[EdgeType] = (
#         EdgeType.CONTAINS,
#         EdgeType.CALLS,
#         EdgeType.EXTENDS,
#         EdgeType.IMPLEMENTS,
#         EdgeType.OVERRIDES,
#     ),
# ):
#     # Keep top-N nodes by priority then degree
#     priority = {
#         NodeType.CLASS: 3,
#         NodeType.INTERFACE: 3,
#         NodeType.ENUM: 2,
#         NodeType.METHOD: 2,
#         NodeType.FUNCTION: 2,
#         NodeType.FILE: 1,
#     }
#     nodes = list(G.g.nodes())
#     scored = []
#     for n in nodes:
#         d = G.g.nodes[n]
#         deg = G.g.degree[n]
#         scored.append((priority.get(d.get("type"), 0), deg, n))
#     scored.sort(reverse=True)
#     keep = set(n for _, _, n in scored[:token_budget_nodes])
#     H = G.subgraph_by_nodes(keep)

#     # strip bulky attrs
#     for n in list(H.g.nodes()):
#         if "doc" in H.g.nodes[n]:
#             H.g.nodes[n]["doc"] = None
#         if "extras" in H.g.nodes[n]:
#             H.g.nodes[n]["extras"] = None

#     # filter edges by type
#     to_drop = []
#     for u, v, e in H.g.edges(keys=True):
#         et = H.g.edges[u, v, e].get("type")
#         if et not in include_edges:
#             to_drop.append((u, v, e))
#     for u, v, e in to_drop:
#         H.g.remove_edge(u, v, key=e)
#     return H
