
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Dict, Any
from .parser_agent import ParserAgent
from .query_agent import QueryAgent
from .types import GraphState, Query

@dataclass
class Orchestrator:
    parser: ParserAgent
    querier: QueryAgent
    state: GraphState

    def route(self, user_msg: str, defaults: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        defaults = defaults or {}
        lower = user_msg.lower()

        # Repo detection
        if "repo" in lower or lower.startswith("build") or "parse" in lower:
            repo = defaults.get("repo") or user_msg.split("repo",1)[-1].strip().strip(':').strip()
            self.state = self.parser.build(self.state, repo)
            return {"ok": True, "action": "build", "repo": repo, "nodes": self.state.nodes, "edges": self.state.edges}

        # Ensure graph exists
        if not self.state.built:
            raise RuntimeError("Graph not built yet. Ask me to build with a repo path.")

        # Controllers / listeners
        if "controller" in lower:
            neighbors = defaults.get("neighbors", 2)
            return {"action": "slice.controllers", **self.querier.slice(self.state, "controllers", neighbors)}
        if "listener" in lower:
            neighbors = defaults.get("neighbors", 2)
            return {"action": "slice.listeners", **self.querier.slice(self.state, "listeners", neighbors)}

        # Pack
        if "pack" in lower or "llm" in lower:
            scenario = "controllers" if "controller" in lower else ("listeners" if "listener" in lower else "controllers")
            out = self.querier.llm_pack(self.state, scenario)
            return {"action": f"llm-pack.{scenario}", **out}

        # Generic query from text
        q = Query(text=user_msg, neighbors=defaults.get("neighbors", 1))
        return {"action": "query", **self.querier.run_query(self.state, q)}
