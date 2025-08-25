# codegraph/tools/endpoint_queries_tool.py
from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
import json
import re
from dataclasses import asdict, is_dataclass

# Import your query engine
from codegraph.queries import GraphIndex, build_index

# ---- Simple in-memory registry so the agent can "load" a graph once and query it later
_REGISTRY: Dict[str, GraphIndex] = {}

def _coerce(obj):
    """Make Node/Edge (dataclasses) JSON-safe."""
    if is_dataclass(obj):
        return asdict(obj)
    if isinstance(obj, (list, tuple)):
        return [_coerce(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _coerce(v) for k, v in obj.items()}
    return obj

# ---------- Tool functions (agent-callable) ----------

def load_graph(graph_id: str, nodes_json: str, edges_json: str) -> Dict[str, Any]:
    """
    Load a graph (nodes, edges) into memory under graph_id.

    nodes_json: JSON array of Node dicts (from your parser output)
    edges_json: JSON array of Edge dicts

    Returns: { "ok": true, "graph_id": ..., "node_count": N, "edge_count": M }
    """
    nodes = json.loads(nodes_json)
    edges = json.loads(edges_json)
    idx = build_index(nodes, edges)  # GraphIndex can accept dict-like nodes/edges
    _REGISTRY[graph_id] = idx
    return {"ok": True, "graph_id": graph_id, "node_count": len(nodes), "edge_count": len(edges)}

def list_controllers(graph_id: str) -> Dict[str, Any]:
    """
    Return fully-qualified names (FQNs) for all controllers (@Controller or @RestController).
    """
    idx = _REGISTRY[graph_id]
    return {"controllers": [c.fqn for c in idx.controllers()]}

def list_endpoints(graph_id: str, controller_fqn: Optional[str] = None) -> Dict[str, Any]:
    """
    List endpoints (methods with HTTP mapping). If controller_fqn is provided, restrict to that class.
    Returns { endpoints: [ {controller, method_fqn, http_methods, combined_paths, ...} ] }
    """
    idx = _REGISTRY[graph_id]
    rows = idx.test_matrix(only_controllers=[controller_fqn] if controller_fqn else None)
    return {"endpoints": rows}

def endpoints_by_method(graph_id: str, http_methods: List[str]) -> Dict[str, Any]:
    """
    Filter endpoints by HTTP verb(s), e.g. ["GET","POST"].
    """
    idx = _REGISTRY[graph_id]
    verbs = {v.upper() for v in (http_methods or [])}
    out = []
    for m in idx.endpoints():
        hb = (m.extras or {}).get("http") or {}
        methods = hb.get("methods") or []
        if any(v in verbs for v in (x.upper() for x in methods)):
            parent = idx.parent_class_of(m.id)
            out.append({
                "controller": parent.fqn if parent else None,
                "method_fqn": m.fqn,
                "http_methods": methods,
                "combined_paths": hb.get("combined_paths") or hb.get("paths") or hb.get("base_paths") or [],
            })
    return {"endpoints": out}

def endpoints_by_path_regex(graph_id: str, pattern: str, use_combined: bool = True) -> Dict[str, Any]:
    """
    Filter endpoints by path regex. Example pattern: '^/admin/.*'.
    use_combined = True to match class+method paths; False to match method-local paths only.
    """
    idx = _REGISTRY[graph_id]
    rx = re.compile(pattern)
    out = []
    for m in idx.endpoints():
        hb = (m.extras or {}).get("http") or {}
        paths = (hb.get("combined_paths") if use_combined else hb.get("paths")) or []
        if any(rx.search(p or "") for p in paths):
            parent = idx.parent_class_of(m.id)
            out.append({
                "controller": parent.fqn if parent else None,
                "method_fqn": m.fqn,
                "http_methods": hb.get("methods") or [],
                "matched_paths": paths,
            })
    return {"endpoints": out}

def endpoints_with_param_source(graph_id: str, source: str) -> Dict[str, Any]:
    """
    Find endpoints that use parameters from a given source: one of
    'path','query','header','body','cookie','part'.
    """
    idx = _REGISTRY[graph_id]
    key = "body_params" if source == "body" else f"{source}_params"
    out = []
    for m in idx.endpoints():
        hb = (m.extras or {}).get("http") or {}
        vals = hb.get(key) or []
        if vals:
            parent = idx.parent_class_of(m.id)
            out.append({
                "controller": parent.fqn if parent else None,
                "method_fqn": m.fqn,
                "http_methods": hb.get("methods") or [],
                "paths": hb.get("combined_paths") or hb.get("paths") or hb.get("base_paths") or [],
                "params": vals,
                "source": source,
            })
    return {"endpoints": out}

def calls_from(graph_id: str, method_fqn: str, depth: int = 1) -> Dict[str, Any]:
    """
    Return a transitive set (up to 'depth') of method IDs called by the given method.
    Uses CALLS edges (best-effort).
    """
    idx = _REGISTRY[graph_id]
    # find node
    target = next((n for n in idx.method_nodes() if n.fqn == method_fqn), None)
    if not target:
        return {"called": [], "warning": f"method not found: {method_fqn}"}
    called = list(idx.calls_from(target, depth=depth))
    return {"called": called}

def endpoint_detail(graph_id: str, method_fqn: str) -> Dict[str, Any]:
    """
    Return a single endpoint row from the test matrix for method_fqn (if any).
    """
    idx = _REGISTRY[graph_id]
    for m in idx.endpoints():
        if m.fqn == method_fqn:
            hb = (m.extras or {}).get("http") or {}
            parent = idx.parent_class_of(m.id)
            return {
                "controller": parent.fqn if parent else None,
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
    return {"warning": f"endpoint not found: {method_fqn}"}

def to_llm_payload(graph_id: str, limit: Optional[int] = None) -> Dict[str, Any]:
    """
    Compact JSON payload of endpoints for LLM controller/listener analysis prompts.
    """
    idx = _REGISTRY[graph_id]
    rows = idx.test_matrix()
    if limit is not None:
        rows = rows[:limit]
    return {"endpoints": rows}

# ---------- Tool manifest (for function-calling / ADK / OpenAI / LangChain) ----------

def tool_spec() -> Dict[str, Any]:
    """
    Return a JSON-schema tool manifest describing the functions.
    """
    return {
        "name": "codegraph_queries",
        "description": (
            "Graph query tool for Java codebases parsed by CodeGraph Toolkit. "
            "Given a pre-loaded graph (nodes+edges), it returns controllers, HTTP endpoints, "
            "filters by verb/path, extracts parameter sources, response status/CORS, and "
            "produces compact payloads for LLM-based controller/listener analyses. "
            "Works with either Tree-sitter or javalang parsers, since both emit the normalized schema."
        ),
        "functions": [
            {
                "name": "load_graph",
                "description": (
                    "Load a graph into the tool under a given graph_id. "
                    "Must be called first in a session. Accepts JSON arrays for nodes and edges "
                    "exactly as emitted by the parsers/graph builder."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "graph_id": {"type": "string", "description": "Arbitrary ID to reference this graph later."},
                        "nodes_json": {"type": "string", "description": "JSON array of Node objects."},
                        "edges_json": {"type": "string", "description": "JSON array of Edge objects."}
                    },
                    "required": ["graph_id", "nodes_json", "edges_json"]
                }
            },
            {
                "name": "list_controllers",
                "description": "List fully-qualified controller names (@Controller or @RestController).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "graph_id": {"type": "string"}
                    },
                    "required": ["graph_id"]
                }
            },
            {
                "name": "list_endpoints",
                "description": "List all HTTP endpoints, optionally restricted to a controller FQN.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "graph_id": {"type": "string"},
                        "controller_fqn": {"type": "string", "nullable": True}
                    },
                    "required": ["graph_id"]
                }
            },
            {
                "name": "endpoints_by_method",
                "description": "Filter endpoints by HTTP verb(s), e.g. GET, POST.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "graph_id": {"type": "string"},
                        "http_methods": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of methods like ['GET','POST']"
                        }
                    },
                    "required": ["graph_id", "http_methods"]
                }
            },
            {
                "name": "endpoints_by_path_regex",
                "description": "Filter endpoints by a regular expression applied to paths.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "graph_id": {"type": "string"},
                        "pattern": {"type": "string", "description": "Python-style regex."},
                        "use_combined": {"type": "boolean", "default": True}
                    },
                    "required": ["graph_id", "pattern"]
                }
            },
            {
                "name": "endpoints_with_param_source",
                "description": "Find endpoints using parameters from a given source: path, query, header, body, cookie, or part.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "graph_id": {"type": "string"},
                        "source": {"type": "string", "enum": ["path","query","header","body","cookie","part"]}
                    },
                    "required": ["graph_id", "source"]
                }
            },
            {
                "name": "calls_from",
                "description": "Return methods called by the given method (best-effort call graph), up to a given depth.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "graph_id": {"type": "string"},
                        "method_fqn": {"type": "string"},
                        "depth": {"type": "integer", "minimum": 1, "default": 1}
                    },
                    "required": ["graph_id", "method_fqn"]
                }
            },
            {
                "name": "endpoint_detail",
                "description": "Get a full HTTP row (paths, methods, params, status, CORS) for a specific method FQN.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "graph_id": {"type": "string"},
                        "method_fqn": {"type": "string"}
                    },
                    "required": ["graph_id", "method_fqn"]
                }
            },
            {
                "name": "to_llm_payload",
                "description": "Compact endpoints JSON for LLM prompts (controller/listener analyses).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "graph_id": {"type": "string"},
                        "limit": {"type": "integer", "minimum": 1}
                    },
                    "required": ["graph_id"]
                }
            }
        ]
    }
