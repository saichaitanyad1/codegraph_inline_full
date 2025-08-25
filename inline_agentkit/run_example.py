
from __future__ import annotations
from inline_agentkit.orchestrator import Orchestrator
from inline_agentkit.parser_agent import ParserAgent
from inline_agentkit.query_agent import QueryAgent
from inline_agentkit.types import GraphState, Query

# 1) Bootstrap agents and state
orch = Orchestrator(parser=ParserAgent(lang="auto"), querier=QueryAgent(), state=GraphState())

# 2) Build (adjust path)
print("# Build")
print(orch.route("Build repo /path/to/repo"))

# 3) Controller slice
print("\n# Controllers slice")
print(orch.route("show controllers two hops", defaults={"neighbors": 2}))

# 4) Query: GET endpoints around Order
print("\n# Query GET endpoints")
print(orch.querier.run_query(orch.state, Query(text="Order", kind="method", annotations_any=["@GetMapping"], neighbors=2)))

# 5) LLM pack
print("\n# LLM pack")
print(orch.querier.llm_pack(orch.state, scenario="controllers", out_dir="./out/llm"))
