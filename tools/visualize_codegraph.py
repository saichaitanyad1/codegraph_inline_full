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

    nodes_json_path: path to nodes.json (array of node dicts)
    edges_json_path: path to edges.json (array of edges with src/dst/type)
    out_png:         path to write PNG diagram
    out_graphml:     optional path to write GraphML
    layout:          graph layout algorithm
    label_by:        which field to prefer for node labels
    show_edge_labels:draw text labels for edge types on the PNG

    Returns the PNG path.
    """
    import json
    import matplotlib.pyplot as plt
    import networkx as nx

    with open(nodes_json_path, 'r', encoding='utf-8') as f:
        nodes = json.load(f)
    with open(edges_json_path, 'r', encoding='utf-8') as f:
        edges = json.load(f)

    # Build networkx DiGraph
    G = nx.DiGraph()
    for n in nodes:
        nid = n.get("id") or n.get("fqn") or n.get("name")
        ntype = n.get("type")
        if hasattr(ntype, "name"):
            ntype = ntype.name
        n["_type_str"] = str(ntype or "UNKNOWN")

        if label_by == "fqn":
            n["_label"] = n.get("fqn") or n.get("name") or n.get("id")
        elif label_by == "name":
            n["_label"] = n.get("name") or n.get("fqn") or n.get("id")
        elif label_by == "id":
            n["_label"] = n.get("id") or n.get("name") or n.get("fqn")
        else:  # auto
            n["_label"] = n.get("fqn") or n.get("name") or n.get("id")

        G.add_node(nid, **n)

    for e in edges:
        src = e.get("src") or e.get("source")
        dst = e.get("dst") or e.get("target")
        et = e.get("type", "EDGE")
        if hasattr(et, "name"):
            et = et.name
        if src and dst:
            G.add_edge(src, dst, type=str(et))

    # Color palette by node type
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
        # size heuristic
        size = 1200
        if t in ("FILE", "PACKAGE"): size = 2000
        elif t in ("CLASS", "INTERFACE", "ENUM"): size = 1600
        elif t == "METHOD": size = 1300
        node_sizes.append(size)
        labels[nid] = data.get("_label", nid)

    # Layout
    if layout == "kamada_kawai":
        pos = nx.kamada_kawai_layout(G)
    elif layout == "circular":
        pos = nx.circular_layout(G)
    elif layout == "shell":
        pos = nx.shell_layout(G)
    else:
        pos = nx.spring_layout(G, seed=42, k=1.0/(1 + max(len(G.nodes()),1)**0.5))

    # Draw
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

    if out_graphml:
        nx.write_graphml(G, out_graphml)

    return out_png
