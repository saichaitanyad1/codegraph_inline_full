
from __future__ import annotations
from typing import Dict, Any, Optional
import re
from .graph_schema import CodeGraph, NodeType, EdgeType

KIND_MAP = {
    "file": NodeType.FILE,
    "class": NodeType.CLASS,
    "interface": NodeType.INTERFACE,
    "enum": NodeType.ENUM,
    "method": NodeType.METHOD,
    "function": NodeType.FUNCTION,
}

def _match_text(s: Optional[str], needle: str) -> bool:
    return bool(s and needle.lower() in s.lower())

def dynamic_query(G: CodeGraph, q: Dict[str, Any]) -> CodeGraph:
    text = q.get("text")
    kind = q.get("kind")
    annos = set(q.get("annotations_any") or [])
    name_regex = q.get("name_regex")
    file_regex = q.get("file_regex")
    calls = q.get("calls")
    implements = q.get("implements")
    extends = q.get("extends")
    neighbors = int(q.get("neighbors") or 0)

    kind_enum = KIND_MAP.get(kind.lower()) if isinstance(kind, str) else None
    name_rx = re.compile(name_regex) if name_regex else None
    file_rx = re.compile(file_regex) if file_regex else None

    seeds = []
    for n, d in G.g.nodes(data=True):
        if kind_enum and d.get("type") != kind_enum:
            continue
        if text and not (
            _match_text(d.get("name"), text)
            or _match_text(d.get("fqn"), text)
            or any(_match_text(a, text) for a in d.get("annotations", []))
            or _match_text(d.get("file"), text)
        ):
            continue
        if annos and not (set(d.get("annotations", [])) & annos):
            continue
        if name_rx and not (name_rx.search(d.get("name") or "") or name_rx.search(d.get("fqn") or "")):
            continue
        if file_rx and not file_rx.search(d.get("file") or ""):
            continue
        seeds.append(n)

    if implements:
        seeds = [n for n in seeds if any(
            data.get("type") == EdgeType.IMPLEMENTS and (
                str(v).endswith(implements) or (G.g.nodes.get(v,{}).get("name"," ").endswith(implements))
            )
            for _, v, data in G.g.out_edges(n, data=True)
        )]
    if extends:
        seeds = [n for n in seeds if any(
            data.get("type") == EdgeType.EXTENDS and (
                str(v).endswith(extends) or (G.g.nodes.get(v,{}).get("name"," ").endswith(extends))
            )
            for _, v, data in G.g.out_edges(n, data=True)
        )]
    if calls:
        seeds = [n for n in seeds if any(
            data.get("type") == EdgeType.CALLS and calls.lower() in (G.g.nodes.get(v,{}).get("fqn"," ") + G.g.nodes.get(v,{}).get("name"," ")).lower()
            for _, v, data in G.g.out_edges(n, data=True)
        )]

    if not seeds:
        return G.subgraph_by_nodes(set())

    return G.neighbors_k_hops(seeds, k=neighbors) if neighbors > 0 else G.subgraph_by_nodes(seeds)
