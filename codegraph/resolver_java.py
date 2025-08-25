
from __future__ import annotations
from typing import List, Dict, Optional
from .graph_schema import CodeGraph, EdgeType, NodeType, Edge

def resolve_calls(G: CodeGraph):
    class_nodes_by_simple: Dict[str, List[str]] = {}
    for nid, data in G.g.nodes(data=True):
        if data.get("type") == NodeType.CLASS:
            simple = (data.get("name") or "").split(".")[-1]
            class_nodes_by_simple.setdefault(simple, []).append(nid)

    def find_class_fqn(simple: str, pkg: Optional[str], imports: List[str]) -> Optional[str]:
        for imp in imports or []:
            if imp.endswith("." + simple) or imp == simple:
                return imp
        if pkg:
            nid = G.by_fqn.get(f"{pkg}.{simple}")
            if nid:
                return f"{pkg}.{simple}"
        for nid in class_nodes_by_simple.get(simple, []):
            return G.g.nodes[nid].get("fqn")
        return None

    calls = []
    for u, v, k, d in G.g.edges(keys=True, data=True):
        if d.get("type") == EdgeType.CALLS:
            calls.append((u, v, k, d))

    for u, v, k, d in calls:
        qual = (d.get("extras") or {}).get("qualifier")
        pkg = (d.get("extras") or {}).get("package")
        imports = (d.get("extras") or {}).get("imports") or []
        member = G.g.nodes[v].get("name") or None

        resolved_class_fqn = None
        if qual:
            # find caller class
            caller_class = None
            for pred, _, ed in G.g.in_edges(u, data=True):
                if ed.get("type") == EdgeType.CONTAINS and G.g.nodes[pred].get("type") == NodeType.CLASS:
                    caller_class = pred; break
            if caller_class:
                fields = (G.g.nodes[caller_class].get("extras") or {}).get("fields", {})
                ftype = fields.get(qual)
                if ftype:
                    resolved_class_fqn = find_class_fqn(ftype, pkg, imports)
            if not resolved_class_fqn and qual[:1].upper() == qual[:1]:
                resolved_class_fqn = find_class_fqn(qual, pkg, imports)
        else:
            caller_class = None
            for pred, _, ed in G.g.in_edges(u, data=True):
                if ed.get("type") == EdgeType.CONTAINS and G.g.nodes[pred].get("type") == NodeType.CLASS:
                    caller_class = pred; break
            if caller_class:
                resolved_class_fqn = G.g.nodes[caller_class].get("fqn")

        if not (resolved_class_fqn and member):
            continue

        target_class_node = G.by_fqn.get(resolved_class_fqn)
        if not target_class_node:
            continue

        method_targets = []
        for _, mn, ed in G.g.out_edges(target_class_node, data=True):
            if ed.get("type") == EdgeType.CONTAINS and G.g.nodes[mn].get("type") == NodeType.METHOD:
                if G.g.nodes[mn].get("name") == member:
                    method_targets.append(mn)

        if not method_targets:
            continue

        G.g.remove_edge(u, v, key=k)
        for t in method_targets:
            G.add_edge(Edge(src=u, dst=t, type=EdgeType.CALLS, extras={"resolved": True}))
