
from __future__ import annotations
from datetime import datetime
from codegraph.graph_builder import build_graph_from_repo
from .types import GraphState

class ParserAgent:
    """Builds or refreshes the code graph from a repo path (inline, no REST)."""
    def __init__(self, lang: str = "auto"):
        self.lang = lang

    def build(self, state: GraphState, repo_ref: str) -> GraphState:
        G = build_graph_from_repo(repo_ref, lang=self.lang)
        state.graph = G
        state.built = True
        state.nodes = G.g.number_of_nodes()
        state.edges = G.g.number_of_edges()
        state.repo_ref = repo_ref
        state.ts = datetime.utcnow().isoformat()
        return state
