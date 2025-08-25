from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

@dataclass
class GraphState:
    built: bool = False
    nodes: int = 0
    edges: int = 0
    graph: Any = None   # CodeGraph instance
    repo_ref: Optional[str] = None
    ts: Optional[str] = None

@dataclass
class Query:
    text: Optional[str] = None
    kind: Optional[str] = None
    annotations_any: list[str] = field(default_factory=list)
    name_regex: Optional[str] = None
    file_regex: Optional[str] = None
    calls: Optional[str] = None
    implements: Optional[str] = None
    extends: Optional[str] = None
    neighbors: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            k: v for k, v in self.__dict__.items() if v not in (None, [], {})
        }