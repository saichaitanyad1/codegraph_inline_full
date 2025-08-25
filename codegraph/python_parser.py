
from __future__ import annotations
import ast
from typing import List, Tuple
from .graph_schema import Node, Edge, NodeType, EdgeType

def parse_python_source(src: str, path: str) -> Tuple[List[Node], List[Edge]]:
    tree = ast.parse(src)
    nodes: List[Node] = []
    edges: List[Edge] = []
    file_id = f"file::{path}"
    nodes.append(Node(id=file_id, type=NodeType.FILE, name=path.split('/')[-1], fqn=path, file=path))

    class_stack = []
    funcs_in_class = {}

    def decos(dec_list):
        out = []
        for d in dec_list or []:
            if isinstance(d, ast.Name):
                out.append(f"@{d.id}")
            elif isinstance(d, ast.Attribute):
                out.append(f"@{d.attr}")
            elif isinstance(d, ast.Call):
                if isinstance(d.func, ast.Name):
                    out.append(f"@{d.func.id}")
                elif isinstance(d.func, ast.Attribute):
                    out.append(f"@{d.func.attr}")
        return out

    class Visitor(ast.NodeVisitor):
        def visit_ClassDef(self, node: ast.ClassDef):
            fqn = ".".join([*class_stack, node.name])
            class_id = f"py::{fqn}"
            cn = Node(id=class_id, type=NodeType.CLASS, name=node.name, fqn=fqn, file=path, line=node.lineno, annotations=decos(node.decorator_list))
            nodes.append(cn)
            edges.append(Edge(src=file_id, dst=class_id, type=EdgeType.CONTAINS))

            # Bases as extends/implements (shallow)
            for b in node.bases:
                if isinstance(b, ast.Name):
                    base_name = b.id
                elif isinstance(b, ast.Attribute):
                    base_name = b.attr
                else:
                    base_name = None
                if base_name:
                    base_fqn = base_name
                    base_id = f"py::{base_fqn}"
                    nodes.append(Node(id=base_id, type=NodeType.CLASS, name=base_name, fqn=base_fqn))
                    edges.append(Edge(src=class_id, dst=base_id, type=EdgeType.EXTENDS))

            class_stack.append(node.name)
            funcs_in_class[fqn] = []
            self.generic_visit(node)
            class_stack.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef):
            if class_stack:
                fqn = ".".join([*class_stack, node.name])
                method_id = f"py::{fqn}"
                mn = Node(id=method_id, type=NodeType.METHOD, name=node.name, fqn=fqn, file=path, line=node.lineno, annotations=decos(node.decorator_list))
                nodes.append(mn)
                class_id = f"py::{'.'.join(class_stack)}"
                edges.append(Edge(src=class_id, dst=method_id, type=EdgeType.CONTAINS))
                funcs_in_class['.'.join(class_stack)].append((method_id, node))
            else:
                fqn = node.name
                fn_id = f"py::{fqn}"
                fn = Node(id=fn_id, type=NodeType.FUNCTION, name=node.name, fqn=fqn, file=path, line=node.lineno, annotations=decos(node.decorator_list))
                nodes.append(fn)
                edges.append(Edge(src=file_id, dst=fn_id, type=EdgeType.CONTAINS))
            self.generic_visit(node)

    v = Visitor()
    v.visit(tree)

    # Collect call edges (simple)
    for class_fqn, items in funcs_in_class.items():
        for method_id, node in items:
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    name = None
                    if isinstance(child.func, ast.Name):
                        name = child.func.id
                        qual = None
                    elif isinstance(child.func, ast.Attribute):
                        name = child.func.attr
                        qual = getattr(child.func.value, "id", None)
                    else:
                        qual = None
                    if name:
                        guess = f"{class_fqn}.{name}"
                        callee_id = f"py::{guess}"
                        edges.append(Edge(src=method_id, dst=callee_id, type=EdgeType.CALLS, extras={"qualifier": qual}))
    return nodes, edges
