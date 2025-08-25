
from __future__ import annotations
from typing import Literal
from .exporters import compact_for_llm

PROMPT_CONTROLLERS = (
    "You are a senior backend reviewer. Analyze the provided code graph focused on web controllers.\n"
    "Goal: identify endpoints, auth boundaries, cross-service calls, and risky patterns.\n"
    "Return a structured report with:\n"
    "1) Endpoint inventory (HTTP method, path if available, controller class, method name).\n"
    "2) Downstream calls per endpoint (internal services, DAOs, http clients).\n"
    "3) Security notes (missing auth/validation, deserialization of request bodies, exception leakage).\n"
    "4) Duplications or dead endpoints (no callers, overlapping paths).\n"
    "5) Suggestions: refactoring and tests.\n"
    "Only use the provided graph. If data is missing, call it out explicitly.\n"
)

PROMPT_LISTENERS = (
    "You are a senior backend reviewer. Analyze the provided code graph focused on event/message listeners.\n"
    "Return a structured report with:\n"
    "1) Listener inventory (annotation or interface, event/topic/queue if available, class.method).\n"
    "2) Fan-in / fan-out: what triggers these listeners and what they call downstream.\n"
    "3) Ordering, retries, idempotency signals; potential dead-letter handling or lack thereof.\n"
    "4) Concurrency hotspots or long-running work in listeners.\n"
    "5) Suggestions: backpressure safeguards, poison message handling, observability.\n"
    "Only use the provided graph. If data is missing, call it out explicitly.\n"
)

def write_llm_pack(G, out_dir: str, prompt_text: str):
    import os, json
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "pack.json"), "w", encoding="utf-8") as f:
        json.dump(G.to_json(), f)
    with open(os.path.join(out_dir, "prompt.txt"), "w", encoding="utf-8") as f:
        f.write(prompt_text)

def build_llm_pack(graph, scenario: Literal["controllers", "listeners"], out_dir: str):
    if scenario == "controllers":
        pack = compact_for_llm(graph, token_budget_nodes=400)
        write_llm_pack(pack, out_dir, PROMPT_CONTROLLERS)
    elif scenario == "listeners":
        pack = compact_for_llm(graph, token_budget_nodes=400)
        write_llm_pack(pack, out_dir, PROMPT_LISTENERS)
    else:
        raise ValueError("unknown scenario")
