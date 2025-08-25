
from __future__ import annotations
from typing import Any, Dict
from codegraph.query_engine import dynamic_query
from codegraph.queries import slice_controllers, slice_listeners
from codegraph.llm_packager import build_llm_pack
from .types import GraphState, Query
import os

class QueryAgent:
    """Translates NL intent to graph filters and runs queries inline."""

    def ensure_graph(self, state: GraphState):
        if not state.built or state.graph is None:
            raise RuntimeError("Graph not built. Ask ParserAgent.build first.")

    def run_query(self, state: GraphState, q: Query) -> Dict[str, Any]:
        self.ensure_graph(state)
        sg = dynamic_query(state.graph, q.to_dict())
        return sg.to_json()

    def slice(self, state: GraphState, kind: str, neighbors: int = 1) -> Dict[str, Any]:
        self.ensure_graph(state)
        if kind == "controllers":
            sg = slice_controllers(state.graph, neighbors=neighbors)
        elif kind == "listeners":
            sg = slice_listeners(state.graph, neighbors=neighbors)
        else:
            raise ValueError("kind must be 'controllers' or 'listeners'")
        return sg.to_json()

    def llm_pack(self, state: GraphState, scenario: str, out_dir: str = "./out/llm") -> Dict[str, Any]:
        self.ensure_graph(state)
        out = os.path.join(out_dir, scenario)
        build_llm_pack(state.graph, scenario, out)
        return {"status": "ok", "out": out}
