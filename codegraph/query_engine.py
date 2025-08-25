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

def dynamic_query(G: CodeGraph, q: Dict[str, Any]):
    text = q.get("text")
    kind = q.get("kind")
    annos = q.get("annotations_any") or []
    name_regex = q.get("name_regex")
    file_regex = q.get("file_regex")
    calls = q.get("calls")
    implements = q.get("implements")
    extends = q.get("extends")
    neighbors = int(q.get("neighbors") or 0)

    # HTTP filters
    http_path_regex = q.get("http_path_regex")
    http_method_any = [m.upper() for m in (q.get("http_method_any") or [])]
    http_produces_any = q.get("http_produces_any") or []
    http_consumes_any = q.get("http_consumes_any") or []
    http_has_path_vars = q.get("http_has_path_vars")

    name_rx = re.compile(name_regex) if name_regex else None
    file_rx = re.compile(file_regex) if file_regex else None
    path_rx = re.compile(http_path_regex) if http_path_regex else None

    def anno_match(d):
        if not annos: return True
        names = [str(x) for x in (d.get("annotations") or [])]
        texts = [str(x) for x in ((d.get("extras", {}) or {}).get("annotation_texts") or [])]
        nlc = {n.lower() for n in names}
        tlc = [t.lower() for t in texts]
        want = {a if a.startswith("@") else f"@{a}" for a in annos}
        return any((w.lower() in nlc) or any(t.startswith(w.lower()) for t in tlc) for w in want)

    seeds = []
    for n, d in G.g.nodes(data=True):
        if kind and d.get("type") != KIND_MAP.get(kind.lower()):
            continue
        if text and not (
            _match_text(d.get("name"), text)
            or _match_text(d.get("fqn"), text)
            or any(_match_text(a, text) for a in d.get("annotations") or [])
            or _match_text(d.get("file"), text)
        ):
            continue
        if not anno_match(d):
            continue
        if name_rx and not (name_rx.search(d.get("name") or "") or name_rx.search(d.get("fqn") or "")):
            continue
        if file_rx and not file_rx.search(d.get("file") or ""):
            continue

        if path_rx or http_method_any or http_produces_any or http_consumes_any or (http_has_path_vars is not None):
            http = (d.get("extras", {}) or {}).get("http") or {}
            paths = (http.get("combined_paths") or []) + (http.get("paths") or [])
            methods = [m.upper() for m in (http.get("methods") or [])]
            produces = http.get("produces") or []
            consumes = http.get("consumes") or []
            path_vars = (http.get("path_variables_in_combined") or [])
            if path_rx and not any(path_rx.search(p or "") for p in paths):
                continue
            if http_method_any and not any(m in methods for m in http_method_any):
                continue
            if http_produces_any and not any(x in produces for x in http_produces_any):
                continue
            if http_consumes_any and not any(x in consumes for x in http_consumes_any):
                continue
            if (http_has_path_vars is True) and not path_vars:
                continue
            if (http_has_path_vars is False) and path_vars:
                continue

        seeds.append(n)

    if not seeds:
        return G.subgraph_by_nodes(set())
    return G.neighbors_k_hops(seeds, k=neighbors) if neighbors > 0 else G.subgraph_by_nodes(seeds)
