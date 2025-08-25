from __future__ import annotations
import ast
from typing import List, Tuple
from .graph_schema import Node, Edge, NodeType, EdgeType

def _decostr(d: ast.AST) -> tuple[str, str, dict]:
    # returns (name_only, full_with_args, args_dict)
    def name_of(n):
        if isinstance(n, ast.Name):
            return n.id
        if isinstance(n, ast.Attribute):
            return n.attr
        return "decorator"
    def arg_to_str(a):
        if isinstance(a, ast.Constant):
            return str(a.value)
        if isinstance(a, ast.Str):
            return a.s
        if isinstance(a, ast.Name):
            return a.id
        if isinstance(a, ast.Attribute):
            return a.attr
        return "expr"
    if isinstance(d, ast.Call):
        nm = name_of(d.func)
        pos = [arg_to_str(x) for x in d.args]
        kw = {k.arg: arg_to_str(k.value) for k in d.keywords}
        args_dict = {**({"args": pos} if pos else {}), **kw}
        inside = ", ".join([*pos, *[f"{k}={v}" for k,v in kw.items()]])
        return f"@{nm}", f"@{nm}({inside})", args_dict
    else:
        nm = name_of(d)
        return f"@{nm}", f"@{nm}", {}

def parse_python_source(src: str, path: str) -> Tuple[List[Node], List[Edge]]:
    tree = ast.parse(src)
    nodes: List[Node] = []
    edges: List[Edge] = []
    file_id = f"file::{path}"
    nodes.append(Node(id=file_id, type=NodeType.FILE, name=path.split('/')[-1], fqn=path, file=path))

    class_stack = []
    funcs_in_class = {}

    class Visitor(ast.NodeVisitor):
        def visit_ClassDef(self, node: ast.ClassDef):
            anns = [_decostr(d) for d in (node.decorator_list or [])]
            anno_names = [a for a,_,_ in anns]
            anno_texts = [b for _,b,_ in anns]
            anno_args = [c for _,_,c in anns]

            fqn = ".".join([*class_stack, node.name])
            class_id = f"py::{fqn}"
            cn = Node(id=class_id, type=NodeType.CLASS, name=node.name, fqn=fqn, file=path, line=node.lineno,
                      annotations=anno_names, extras={"annotation_texts": anno_texts, "annotation_args": anno_args})
            nodes.append(cn)
            edges.append(Edge(src=file_id, dst=class_id, type=EdgeType.CONTAINS))

            # Bases as extends (shallow)
            for b in node.bases:
                base_name = getattr(b, 'id', None) or getattr(b, 'attr', None)
                if base_name:
                    base_id = f"py::{base_name}"
                    nodes.append(Node(id=base_id, type=NodeType.CLASS, name=base_name, fqn=base_name))
                    edges.append(Edge(src=class_id, dst=base_id, type=EdgeType.EXTENDS))

            class_stack.append(node.name)
            funcs_in_class[fqn] = []
            self.generic_visit(node)
            class_stack.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef):
            anns = [_decostr(d) for d in (node.decorator_list or [])]
            anno_names = [a for a,_,_ in anns]
            anno_texts = [b for _,b,_ in anns]
            anno_args = [c for _,_,c in anns]

            if class_stack:
                fqn = ".".join([*class_stack, node.name])
                method_id = f"py::{fqn}"
                mn = Node(id=method_id, type=NodeType.METHOD, name=node.name, fqn=fqn, file=path, line=node.lineno,
                          annotations=anno_names, extras={"annotation_texts": anno_texts, "annotation_args": anno_args})
                nodes.append(mn)
                class_id = f"py::{'.'.join(class_stack)}"
                edges.append(Edge(src=class_id, dst=method_id, type=EdgeType.CONTAINS))
                funcs_in_class['.'.join(class_stack)].append((method_id, node))
            else:
                fqn = node.name
                fn_id = f"py::{fqn}"
                fn = Node(id=fn_id, type=NodeType.FUNCTION, name=node.name, fqn=fqn, file=path, line=node.lineno,
                          annotations=anno_names, extras={"annotation_texts": anno_texts, "annotation_args": anno_args})
                nodes.append(fn)
                edges.append(Edge(src=file_id, dst=fn_id, type=EdgeType.CONTAINS))
            self.generic_visit(node)

    v = Visitor(); v.visit(tree)

    # Simple call edges inside methods
    for class_fqn, items in funcs_in_class.items():
        for method_id, node in items:
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    name = None; qual = None
                    if isinstance(child.func, ast.Name):
                        name = child.func.id
                    elif isinstance(child.func, ast.Attribute):
                        name = child.func.attr
                        qual = getattr(child.func.value, "id", None)
                    if name:
                        guess = f"{class_fqn}.{name}"
                        callee_id = f"py::{guess}"
                        edges.append(Edge(src=method_id, dst=callee_id, type=EdgeType.CALLS, extras={"qualifier": qual}))
    return nodes, edges