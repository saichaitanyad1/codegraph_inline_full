#!/usr/bin/env python3
"""
End-to-end test script:
- Build graph(s) from a repo
- Slice controllers
- Export JSON
- Dump nodes/edges for visualization
- Render PNG + GraphML inline (no external CLI step)
"""

import sys
import os
import json
from dataclasses import asdict, is_dataclass

import matplotlib.pyplot as plt
import networkx as nx

# --- Project imports ---------------------------------------------------------
# Make "codegraph" importable when run from repo root
ROOT_DIR = os.path.dirname(__file__)
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, os.path.join(ROOT_DIR, 'codegraph'))

from codegraph.graph_builder import build_graph_from_repo
from codegraph.java_parser_treesitter import parse_java_source_ts  # noqa: F401 (imported for completeness)
from codegraph.exporters import export_json
from codegraph.manual_queries import slice_controllers


# --- Helpers ----------------------------------------------------------------
def call_build_graph_from_repo(repo_path: str, lang: str = "auto"):
    return build_graph_from_repo(repo_path, lang)


def ensure_outdir(path: str):
    os.makedirs(path, exist_ok=True)


def dump_nodes_edges_inline(graph, out_dir: str, prefix: str = ""):
    """
    Create {prefix}nodes.json and {prefix}edges.json in out_dir.

    Works whether your graph keeps dataclass lists (graph.nodes/graph.edges)
    or just a NetworkX DiGraph at graph.g.
    """
    ensure_outdir(out_dir)

    # Prefer explicit lists if present
    nodes_list = getattr(graph, 'nodes', None) or []
    edges_list = getattr(graph, 'edges', None) or []

    if not nodes_list or not edges_list:
        # Fallback: derive from NetworkX graph
        g = getattr(graph, 'g', None)
        if g is None:
            raise RuntimeError("Graph has neither dataclass lists nor .g DiGraph")

        nodes_list = []
        for nid, data in g.nodes(data=True):
            d = dict(data)
            d.setdefault('id', nid)
            nodes_list.append(d)

        edges_list = []
        for u, v, ed in g.edges(data=True):
            et = ed.get('type')
            if hasattr(et, 'name'):
                et = et.name
            edges_list.append({'src': u, 'dst': v, 'type': et or 'EDGE'})

    # Coerce to plain dicts
    def _plain(o):
        if isinstance(o, dict):
            return o
        if is_dataclass(o):
            return asdict(o)
        d = {}
        for k in ("id", "type", "name", "fqn", "file", "line", "annotations", "params", "returns", "extras", "src", "dst"):
            if hasattr(o, k):
                d[k] = getattr(o, k)
        return d

    nodes_json = [_plain(n) for n in nodes_list]
    edges_json = [_plain(e) for e in edges_list]

    np = os.path.join(out_dir, f"{prefix}nodes.json")
    ep = os.path.join(out_dir, f"{prefix}edges.json")
    with open(np, 'w', encoding='utf-8') as f:
        json.dump(nodes_json, f, indent=2)
    with open(ep, 'w', encoding='utf-8') as f:
        json.dump(edges_json, f, indent=2)
    return np, ep


def visualize_codegraph(
    nodes_json_path: str,
    edges_json_path: str,
    out_png: str,
    out_graphml: str | None = None,
    *,
    layout: str = "spring",              # spring | kamada_kawai | circular | shell
    label_by: str = "auto",              # auto | fqn | name | id
    show_edge_labels: bool = True,
) -> str:
    """
    Render a CodeGraph (nodes/edges JSON) to a PNG diagram and optional GraphML.
    GraphML is sanitized to only contain scalar attributes; complex attrs are packed into 'data_json'.
    """
    import json
    import matplotlib.pyplot as plt
    import networkx as nx

    # ---------- load ----------
    with open(nodes_json_path, 'r', encoding='utf-8') as f:
        nodes = json.load(f)
    with open(edges_json_path, 'r', encoding='utf-8') as f:
        edges = json.load(f)

    # ---------- build draw-graph (rich attrs) ----------
    G = nx.DiGraph()

    def _scalar(x):
        return isinstance(x, (str, int, float, bool)) or x is None

    def _label_for(n: dict) -> str:
        if label_by == "fqn":
            return n.get("fqn") or n.get("name") or n.get("id")
        if label_by == "name":
            return n.get("name") or n.get("fqn") or n.get("id")
        if label_by == "id":
            return n.get("id") or n.get("name") or n.get("fqn")
        return n.get("fqn") or n.get("name") or n.get("id")

    for n in nodes:
        nid = n.get("id") or n.get("fqn") or n.get("name")
        ntype = n.get("type")
        if hasattr(ntype, "name"):
            ntype = ntype.name
        n["_type_str"] = str(ntype or "UNKNOWN")
        n["_label"] = _label_for(n)
        G.add_node(nid, **n)

    # ... inside visualize_codegraph, after building nodes ...

    for e in edges:
        src = e.get("src") or e.get("source")
        dst = e.get("dst") or e.get("target")
        et = e.get("type", "EDGE")
        if hasattr(et, "name"):
            et = et.name
        if not (src and dst):
            continue

        # Build attrs without conflicting keys
        attrs = {k: v for k, v in e.items() if k not in ("src", "dst", "source", "target", "type")}
        attrs["type"] = str(et)  # single authoritative 'type'
        G.add_edge(src, dst, **attrs)


    # ---------- draw ----------
    palette = {
        "FILE": "#B0BEC5", "PACKAGE": "#FFE082",
        "CLASS": "#90CAF9", "INTERFACE": "#64B5F6", "ENUM": "#4FC3F7",
        "METHOD": "#A5D6A7", "FIELD": "#C5E1A5",
        "IMPORT": "#FFB74D", "ANNOTATION": "#F8BBD0",
        "UNKNOWN": "#E0E0E0",
    }

    node_colors, node_sizes, labels = [], [], {}
    for nid, data in G.nodes(data=True):
        t = data.get("_type_str", "UNKNOWN")
        node_colors.append(palette.get(t, palette["UNKNOWN"]))
        size = 1200
        if t in ("FILE", "PACKAGE"): size = 2000
        elif t in ("CLASS", "INTERFACE", "ENUM"): size = 1600
        elif t == "METHOD": size = 1300
        node_sizes.append(size)
        labels[nid] = data.get("_label", nid)

    if layout == "kamada_kawai":
        pos = nx.kamada_kawai_layout(G)
    elif layout == "circular":
        pos = nx.circular_layout(G)
    elif layout == "shell":
        pos = nx.shell_layout(G)
    else:
        pos = nx.spring_layout(G, seed=42, k=1.0/(1 + max(len(G.nodes()),1)**0.5))

    plt.figure(figsize=(18, 13))
    nx.draw_networkx_nodes(G, pos, node_color=node_colors, node_size=node_sizes,
                           edgecolors="#37474F", linewidths=0.8)
    nx.draw_networkx_labels(G, pos, labels=labels, font_size=7)
    nx.draw_networkx_edges(G, pos, arrows=True, arrowstyle="-|>", arrowsize=12,
                           width=1.0, alpha=0.85)
    if show_edge_labels:
        edge_labels = nx.get_edge_attributes(G, "type")
        nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels, font_size=6)
    plt.axis("off")
    plt.tight_layout()
    plt.savefig(out_png, dpi=220)
    plt.close()

    # ---------- GraphML (sanitized) ----------
    if out_graphml:
        # Build a GraphML-safe copy with only scalar attrs; pack the rest as JSON
        Gml = nx.DiGraph()
        for nid, data in G.nodes(data=True):
            safe = {}
            packed = {}
            for k, v in data.items():
                if _scalar(v):
                    safe[k] = v
                else:
                    packed[k] = v
            if packed:
                safe["data_json"] = json.dumps(packed, ensure_ascii=False, sort_keys=True)
            Gml.add_node(nid, **safe)

        for u, v, data in G.edges(data=True):
            safe = {}
            packed = {}
            for k, vv in data.items():
                if _scalar(vv):
                    safe[k] = vv
                else:
                    packed[k] = vv
            if packed:
                safe["data_json"] = json.dumps(packed, ensure_ascii=False, sort_keys=True)
            Gml.add_edge(u, v, **safe)

        nx.write_graphml(Gml, out_graphml)

    print(f"Rendered: {out_png} & {out_graphml}")
    return out_png


# --- Main -------------------------------------------------------------------
if __name__ == "__main__":
    base_path = "/Users/saichaitanyadarla/Documents/java"   # <-- change if needed
    out_dir = os.path.join(ROOT_DIR, 'out')
    ensure_outdir(out_dir)

    # Build main graph
    print("Building graph from current directory...")
    graph = call_build_graph_from_repo(base_path)
    print(f"Graph has {len(graph.g.nodes)} nodes and {len(graph.g.edges)} edges")

    # Controllers slice
    print("Slicing controllers...")
    controllers_graph = slice_controllers(graph, neighbors=1)
    print(f"Controllers slice has {len(controllers_graph.g.nodes)} nodes")

    # Export (legacy)
    export_json(graph, os.path.join(out_dir, "code_graph.json"))
    export_json(controllers_graph, os.path.join(out_dir, "controllers_graph.json"))

    # Dump nodes/edges
    full_nodes, full_edges = dump_nodes_edges_inline(graph, out_dir, prefix="full_")
    ctrl_nodes, ctrl_edges = dump_nodes_edges_inline(controllers_graph, out_dir, prefix="controllers_")

    # Render images + GraphML
    visualize_codegraph(full_nodes, full_edges,
                        os.path.join(out_dir, "full_graph.png"),
                        os.path.join(out_dir, "full_graph.graphml"),
                        layout="spring", label_by="auto", show_edge_labels=True)

    visualize_codegraph(ctrl_nodes, ctrl_edges,
                        os.path.join(out_dir, "controllers_graph.png"),
                        os.path.join(out_dir, "controllers_graph.graphml"),
                        layout="spring", label_by="auto", show_edge_labels=True)

    # Java-only pass
    print("Building Java-only graph...")
    java_graph = call_build_graph_from_repo(base_path, lang="java")
    java_controllers = slice_controllers(java_graph, neighbors=1)

    export_json(java_graph, os.path.join(out_dir, "java_graph.json"))
    export_json(java_controllers, os.path.join(out_dir, "java_controllers.json"))

    j_nodes, j_edges = dump_nodes_edges_inline(java_graph, out_dir, prefix="java_")
    jc_nodes, jc_edges = dump_nodes_edges_inline(java_controllers, out_dir, prefix="java_controllers_")

    visualize_codegraph(j_nodes, j_edges,
                        os.path.join(out_dir, "java_graph.png"),
                        os.path.join(out_dir, "java_graph.graphml"),
                        layout="spring", label_by="auto")

    visualize_codegraph(jc_nodes, jc_edges,
                        os.path.join(out_dir, "java_controllers_graph.png"),
                        os.path.join(out_dir, "java_controllers_graph.graphml"),
                        layout="spring", label_by="auto")
