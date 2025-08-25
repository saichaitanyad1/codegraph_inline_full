
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any, Dict, Iterable, List, Optional, Set
import networkx as nx
from enum import Enum
import json

class NodeType(str, Enum):
    FILE = "file"
    CLASS = "class"
    INTERFACE = "interface"
    ENUM = "enum"
    METHOD = "method"
    FUNCTION = "function"

class EdgeType(str, Enum):
    CONTAINS = "contains"
    EXTENDS = "extends"
    IMPLEMENTS = "implements"
    OVERRIDES = "overrides"
    CALLS = "calls"
    ANNOTATED_BY = "annotated_by"
    IMPORTS = "imports"

@dataclass
class Node:
    id: str
    type: NodeType
    name: Optional[str]=None
    fqn: Optional[str]=None
    file: Optional[str]=None
    line: Optional[int]=None
    modifiers: Optional[list]=None
    annotations: Optional[list]=None
    params: Optional[list]=None
    returns: Optional[str]=None
    extras: Optional[dict]=None

@dataclass
class Edge:
    src: str
    dst: str
    type: EdgeType
    extras: Optional[dict]=None

class CodeGraph:
    def __init__(self):
        self.g = nx.MultiDiGraph()
        self.by_fqn: Dict[str, str] = {}

    def add_node(self, n: Node):
        if n.id not in self.g:
            self.g.add_node(n.id)
        data = asdict(n)
        self.g.nodes[n.id].update({k:v for k,v in data.items() if v is not None})
        if n.fqn:
            self.by_fqn[n.fqn] = n.id

    def add_edge(self, e: Edge):
        self.g.add_edge(e.src, e.dst, type=e.type, extras=e.extras or {})

    def to_json(self) -> Dict[str, Any]:
        nodes = []
        for nid, d in self.g.nodes(data=True):
            out = dict(id=nid); out.update(d); nodes.append(out)
        edges = []
        for u,v,k,d in self.g.edges(keys=True, data=True):
            edges.append(dict(src=u, dst=v, type=d.get("type"), extras=d.get("extras", {})))
        return {"nodes": nodes, "edges": edges}

    def subgraph_by_nodes(self, ids: Iterable[str]) -> "CodeGraph":
        sg_ids = set(ids)
        H = CodeGraph()
        for n in sg_ids:
            if n in self.g:
                H.add_node(Node(id=n, type=self.g.nodes[n].get("type"),
                                name=self.g.nodes[n].get("name"),
                                fqn=self.g.nodes[n].get("fqn"),
                                file=self.g.nodes[n].get("file"),
                                line=self.g.nodes[n].get("line"),
                                modifiers=self.g.nodes[n].get("modifiers"),
                                annotations=self.g.nodes[n].get("annotations"),
                                params=self.g.nodes[n].get("params"),
                                returns=self.g.nodes[n].get("returns"),
                                extras=self.g.nodes[n].get("extras")))
        for u,v,k,d in self.g.edges(keys=True, data=True):
            if u in sg_ids and v in sg_ids:
                H.add_edge(Edge(src=u, dst=v, type=d.get("type"), extras=d.get("extras", {})))
        return H

    def neighbors_k_hops(self, seeds: Iterable[str], k: int=1) -> "CodeGraph":
        keep: Set[str] = set()
        frontier: Set[str] = set(seeds)
        for _ in range(max(0, k)):
            next_frontier: Set[str] = set()
            for n in frontier:
                keep.add(n)
                for _, v, _ in self.g.out_edges(n, keys=True):
                    keep.add(v); next_frontier.add(v)
                for u, _, _ in self.g.in_edges(n, keys=True):
                    keep.add(u); next_frontier.add(u)
            frontier = next_frontier
        keep |= set(seeds)
        return self.subgraph_by_nodes(keep)
    
    def export_json(self, path: str):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_json(), f, indent=2)

    def export_graphml(self, path: str):
        nx.write_graphml(self.g, path)

    def export_mermaid(self, path: str, node_limit: int = 200):
        lines = ["flowchart LR"]
        nodes = list(self.g.nodes)[:node_limit]
        node_set = set(nodes)
        for n in nodes:
            data = self.g.nodes[n]
            label = (data.get("name", n) or "").replace('"', "'")
            lines.append(f'  {n}["{label}\\n({data.get("type")})"]')
        count = 0
        for u, v, d in self.g.edges(data=True):
            if u in node_set and v in node_set:
                et = d.get("type", "EDGE")
                lines.append(f"  {u} -->|{et}| {v}")
                count += 1
                if count > 800:
                    break
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
