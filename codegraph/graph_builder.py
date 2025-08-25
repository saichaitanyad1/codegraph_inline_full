
from __future__ import annotations
import os, io
from .graph_schema import CodeGraph, Node, Edge, NodeType, EdgeType
from .java_parser import parse_java_source
from .python_parser import parse_python_source
from .resolver_java import resolve_calls as resolve_calls_java

def build_graph_from_repo(repo_path: str, lang: str = "auto") -> CodeGraph:
    G = CodeGraph()
    for root, _, files in os.walk(repo_path):
        for fn in files:
            path = os.path.join(root, fn)
            ext = os.path.splitext(fn)[1].lower()
            if lang == "java" or (lang == "auto" and ext == ".java"):
                try:
                    with io.open(path, "r", encoding="utf-8", errors="ignore") as f:
                        src = f.read()
                    nodes, edges = parse_java_source(src, path)
                    for n in nodes: G.add_node(n)
                    for e in edges: G.add_edge(e)
                except Exception as e:
                    file_id = f"file::{path}"
                    G.add_node(Node(id=file_id, type=NodeType.FILE, name=fn, fqn=path, file=path, extras={"parse_error": str(e)}))
            elif lang == "python" or (lang == "auto" and ext == ".py"):
                try:
                    with io.open(path, "r", encoding="utf-8", errors="ignore") as f:
                        src = f.read()
                    nodes, edges = parse_python_source(src, path)
                    for n in nodes: G.add_node(n)
                    for e in edges: G.add_edge(e)
                except Exception as e:
                    file_id = f"file::{path}"
                    G.add_node(Node(id=file_id, type=NodeType.FILE, name=fn, fqn=path, file=path, extras={"parse_error": str(e)}))
    derive_overrides(G)
    resolve_calls_java(G)
    return G

def derive_overrides(G: CodeGraph):
    supers = {}
    for u, v, d in G.g.edges(data=True):
        if d.get("type") == EdgeType.EXTENDS:
            supers.setdefault(u, set()).add(v)

    class_methods = {}
    for nid, data in G.g.nodes(data=True):
        if data.get("type") == NodeType.METHOD:
            fqn = data.get("fqn") or ""
            cls = fqn.rsplit(".", 1)[0] if "." in fqn else None
            name = data.get("name")
            arity = len(data.get("params", [])) if data.get("params") else 0
            if cls:
                class_methods.setdefault(cls, []).append((nid, name, arity))

    for cls, meths in class_methods.items():
        cls_node_id = G.by_fqn.get(cls)
        if not cls_node_id: 
            continue
        seen = set()
        queue = list(supers.get(cls_node_id, []))
        while queue:
            cur = queue.pop()
            if cur in seen: 
                continue
            seen.add(cur)
            for _, sup, d in G.g.out_edges(cur, data=True):
                if d.get("type") == EdgeType.EXTENDS and sup not in seen:
                    queue.append(sup)

        super_meths = []
        for sn in seen:
            for _, mn, d in G.g.out_edges(sn, data=True):
                if d.get("type") == EdgeType.CONTAINS and G.g.nodes[mn].get("type") == NodeType.METHOD:
                    mdata = G.g.nodes[mn]
                    super_meths.append((mn, mdata.get("name"), len(mdata.get("params", [])) if mdata.get("params") else 0))

        super_index = {}
        for mn, name, ar in super_meths:
            super_index.setdefault((name, ar), []).append(mn)

        for nid, name, ar in meths:
            for super_n in super_index.get((name, ar), []):
                G.add_edge(Edge(src=nid, dst=super_n, type=EdgeType.OVERRIDES))
