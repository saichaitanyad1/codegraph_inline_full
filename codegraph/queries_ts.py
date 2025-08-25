# codegraph/queries.py
from __future__ import annotations
from typing import Iterable, List, Dict, Any, Tuple, Optional, Set, Callable
import re
import json
from collections import defaultdict

# Minimal type duck-typing: we only rely on .id, .type.name, .fqn, .name, .extras, etc.
NodeLike = Any
EdgeLike = Any

HTTP = "http"

# ---------------------------
# Core indexing
# ---------------------------

class GraphIndex:
    """
    Lightweight index over Node/Edge lists produced by either the javalang parser
    or the Tree-sitter parser. No external deps.
    """
    def __init__(self, nodes: Iterable[NodeLike], edges: Iterable[EdgeLike]):
        self.nodes: List[NodeLike] = list(nodes)
        self.edges: List[EdgeLike] = list(edges)

        self.by_id: Dict[str, NodeLike] = {}
        self.by_type: Dict[str, List[NodeLike]] = defaultdict(list)
        self.contains: Dict[str, List[str]] = defaultdict(list)        # CONTAINS: src -> [dst]
        self.rev_contains: Dict[str, str] = {}                         # dst -> src
        self.calls: Dict[str, List[str]] = defaultdict(list)           # CALLS: src method -> [dst method guesses]
        self.ann_idx: Dict[str, List[NodeLike]] = defaultdict(list)    # annotation name -> nodes

        # Build indices
        for n in self.nodes:
            self.by_id[n.id] = n
            tname = getattr(getattr(n, "type", None), "name", None) or str(getattr(n, "type", None))
            self.by_type[tname].append(n)
            for ann in (getattr(n, "annotations", None) or []):
                self.ann_idx[ann].append(n)

        for e in self.edges:
            etype = getattr(getattr(e, "type", None), "name", None) or str(getattr(e, "type", None))
            if etype == "CONTAINS":
                self.contains[e.src].append(e.dst)
                self.rev_contains[e.dst] = e.src
            elif etype == "CALLS":
                self.calls[e.src].append(e.dst)

    # ----------------------------------
    # Node helpers
    # ----------------------------------

    def file_nodes(self) -> List[NodeLike]:
        return self.by_type.get("FILE", [])

    def class_nodes(self) -> List[NodeLike]:
        return self.by_type.get("CLASS", []) + self.by_type.get("INTERFACE", []) + self.by_type.get("ENUM", [])

    def method_nodes(self) -> List[NodeLike]:
        return self.by_type.get("METHOD", [])

    def methods_in_class(self, class_id: str) -> List[NodeLike]:
        return [self.by_id[cid] for cid in self.contains.get(class_id, []) if self.by_id.get(cid) and getattr(self.by_id[cid].type, "name", "") == "METHOD"]

    def parent_class_of(self, node_id: str) -> Optional[NodeLike]:
        cid = self.rev_contains.get(node_id)
        if cid:
            n = self.by_id.get(cid)
            if n and getattr(n.type, "name", "") in {"CLASS", "INTERFACE", "ENUM"}:
                return n
        return None

    # ----------------------------------
    # Annotation queries
    # ----------------------------------

    def nodes_with_annotation(self, ann_name: str) -> List[NodeLike]:
        """
        ann_name must match what parsers emit, e.g. '@Controller', '@RestController', '@GetMapping'
        """
        return self.ann_idx.get(ann_name, [])

    # ----------------------------------
    # HTTP endpoint queries
    # ----------------------------------

    def is_controller(self, node: NodeLike) -> bool:
        anns = set(getattr(node, "annotations", []) or [])
        return any(a in anns for a in ("@Controller", "@RestController"))

    def controllers(self) -> List[NodeLike]:
        return [n for n in self.class_nodes() if self.is_controller(n)]

    def _http_block(self, node: NodeLike) -> Optional[Dict[str, Any]]:
        return ((getattr(node, "extras", {}) or {}).get(HTTP) if getattr(node, "extras", None) else None)

    def endpoints(self, controller_fqn: Optional[str] = None) -> List[NodeLike]:
        """
        All METHOD nodes that have HTTP mapping (either method-level or inherited via class base).
        If controller_fqn is provided, restrict to that controller class.
        """
        out = []
        for m in self.method_nodes():
            hb = self._http_block(m)
            if not hb:
                continue
            methods = hb.get("methods") or []
            base = hb.get("base_paths") or []
            paths = hb.get("paths") or []
            combined = hb.get("combined_paths") or []
            if not (methods or base or paths or combined):
                continue
            if controller_fqn:
                parent = self.parent_class_of(m.id)
                if not parent or parent.fqn != controller_fqn:
                    continue
            out.append(m)
        return out

    def endpoints_by_method(self, *verbs: str) -> List[NodeLike]:
        verbs_up = {v.upper() for v in verbs}
        out = []
        for m in self.endpoints():
            methods = (self._http_block(m) or {}).get("methods") or []
            if any(v.upper() in verbs_up for v in methods):
                out.append(m)
        return out

    def endpoints_by_path_regex(self, pattern: str, use_combined: bool = True) -> List[NodeLike]:
        rx = re.compile(pattern)
        out = []
        for m in self.endpoints():
            hb = self._http_block(m) or {}
            paths = (hb.get("combined_paths") if use_combined else hb.get("paths")) or []
            if any(rx.search(p or "") for p in paths):
                out.append(m)
        return out

    def endpoints_with_missing_paths(self) -> List[NodeLike]:
        out = []
        for m in self.endpoints():
            hb = self._http_block(m) or {}
            if not (hb.get("paths") or hb.get("combined_paths") or hb.get("base_paths")):
                out.append(m)
        return out

    def endpoints_with_param_source(self, source: str) -> List[NodeLike]:
        """
        source ∈ {'path','query','header','body','cookie','part'}
        """
        out = []
        for m in self.endpoints():
            hb = self._http_block(m) or {}
            key = f"{source}_params" if source != "body" else "body_params"
            vals = hb.get(key) or []
            if vals:
                out.append(m)
        return out

    def endpoints_by_query_param(self, name: str) -> List[NodeLike]:
        out = []
        for m in self.endpoints():
            hb = self._http_block(m) or {}
            if name in (hb.get("query_params") or []):
                out.append(m)
        return out

    def endpoints_by_path_variable(self, name: str) -> List[NodeLike]:
        out = []
        for m in self.endpoints():
            hb = self._http_block(m) or {}
            if name in (hb.get("path_variables") or []):
                out.append(m)
        return out

    def endpoints_with_status(self, status_suffix: str) -> List[NodeLike]:
        """
        status_suffix examples: 'OK', 'CREATED', 'NO_CONTENT', or full 'HttpStatus.OK'
        """
        out = []
        status_suffix = status_suffix.upper()
        for m in self.endpoints():
            hb = self._http_block(m) or {}
            st = (hb.get("response_status") or "")
            if st and (st.upper().endswith(status_suffix) or st.upper() == status_suffix):
                out.append(m)
        return out

    def endpoints_with_cors(self) -> List[NodeLike]:
        out = []
        for m in self.endpoints():
            hb = self._http_block(m) or {}
            if hb.get("cors"):
                out.append(m)
        return out

    # ----------------------------------
    # Call graph helpers
    # ----------------------------------

    def calls_from(self, method_node: NodeLike, depth: int = 1) -> Set[str]:
        """
        Return a set of method IDs that are directly (or transitively up to depth) called by method_node.
        Uses the best-effort CALLS edges from the parsers.
        """
        seen: Set[str] = set()
        frontier: Set[str] = {method_node.id}
        for _ in range(max(0, depth)):
            new_frontier: Set[str] = set()
            for mid in frontier:
                for dst in self.calls.get(mid, []):
                    if dst not in seen:
                        seen.add(dst)
                        new_frontier.add(dst)
            frontier = new_frontier
            if not frontier:
                break
        return seen

    # ----------------------------------
    # Test matrix & LLM payloads
    # ----------------------------------

    def test_matrix(self, only_controllers: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Produce a structured matrix of endpoints suitable for generating integration tests.
        """
        out: List[Dict[str, Any]] = []
        allowed = set(only_controllers or [])
        for m in self.endpoints():
            parent = self.parent_class_of(m.id)
            if not parent:
                continue
            if allowed and parent.fqn not in allowed:
                continue
            hb = self._http_block(m) or {}
            row = {
                "controller": parent.fqn,
                "method_fqn": m.fqn,
                "http_methods": hb.get("methods", []),
                "paths": hb.get("paths", []),
                "base_paths": hb.get("base_paths", []),
                "combined_paths": hb.get("combined_paths", []) or (hb.get("paths", []) or hb.get("base_paths", [])),
                "consumes": hb.get("consumes", []),
                "produces": hb.get("produces", []),
                "path_variables": hb.get("path_variables", []),
                "query_params": hb.get("query_params", []),
                "header_params": hb.get("header_params", []),
                "body_params": hb.get("body_params", []),
                "cookie_params": hb.get("cookie_params", []),
                "param_sources": hb.get("param_sources", []),
                "response_status": hb.get("response_status"),
                "cors": hb.get("cors"),
            }
            out.append(row)
        return out

    def to_llm_payload(self, filter_fn: Optional[Callable[[Dict[str, Any]], bool]] = None, limit: Optional[int] = None) -> Dict[str, Any]:
        """
        Compact JSON payload for LLMs: endpoints with just what’s needed for controller/listener analyses.
        """
        rows = self.test_matrix()
        if filter_fn:
            rows = [r for r in rows if filter_fn(r)]
        if limit is not None:
            rows = rows[:limit]
        return {"endpoints": rows}

    # ----------------------------------
    # Convenience pretty-printers
    # ----------------------------------

    def print_endpoints(self, controller_fqn: Optional[str] = None) -> None:
        for m in self.endpoints(controller_fqn):
            hb = self._http_block(m) or {}
            parent = self.parent_class_of(m.id)
            methods = ",".join(hb.get("methods", []) or ["<NONE>"])
            paths = hb.get("combined_paths") or hb.get("paths") or hb.get("base_paths") or []
            print(f"- {parent.fqn if parent else '<unknown>'} :: {m.name} -> [{methods}] {paths}")

# ---------------------------
# Public helper functions
# ---------------------------

def build_index(nodes: Iterable[NodeLike], edges: Iterable[EdgeLike]) -> GraphIndex:
    return GraphIndex(nodes, edges)

def list_controllers(idx: GraphIndex) -> List[str]:
    return [c.fqn for c in idx.controllers()]

def list_endpoints(idx: GraphIndex, controller_fqn: Optional[str] = None) -> List[Tuple[str, List[str], List[str]]]:
    out = []
    for m in idx.endpoints(controller_fqn):
        hb = idx._http_block(m) or {}
        out.append((m.fqn, hb.get("methods", []), hb.get("combined_paths") or hb.get("paths") or []))
    return out

def endpoints_by_method(idx: GraphIndex, *verbs: str) -> List[str]:
    return [m.fqn for m in idx.endpoints_by_method(*verbs)]

def endpoints_by_path_regex(idx: GraphIndex, pattern: str, use_combined: bool = True) -> List[str]:
    return [m.fqn for m in idx.endpoints_by_path_regex(pattern, use_combined)]

def endpoints_with_param_source(idx: GraphIndex, source: str) -> List[str]:
    return [m.fqn for m in idx.endpoints_with_param_source(source)]

def generate_llm_json(idx: GraphIndex, limit: Optional[int] = None) -> str:
    return json.dumps(idx.to_llm_payload(limit=limit), indent=2)
