
from __future__ import annotations
from typing import List, Tuple, Dict
import javalang
from .graph_schema import Node, Edge, NodeType, EdgeType

def parse_java_source(src: str, path: str) -> Tuple[List[Node], List[Edge]]:
    tree = javalang.parse.parse(src)
    package_name = tree.package.name if tree.package else None
    imports = [imp.path for imp in tree.imports] if tree.imports else []

    nodes: List[Node] = []
    edges: List[Edge] = []

    file_id = f"file::{path}"
    nodes.append(Node(id=file_id, type=NodeType.FILE, name=path.split('/')[-1], fqn=path, file=path))

    def fqn(name: str) -> str:
        return f"{package_name}.{name}" if package_name else name

    def anno_list(annos):
        out = []
        for a in annos or []:
            if hasattr(a, "name"):
                out.append(f"@{a.name}")
        return out

    for type_decl in tree.types:
        if isinstance(type_decl, javalang.tree.ClassDeclaration):
            ntype = NodeType.CLASS
        elif isinstance(type_decl, javalang.tree.InterfaceDeclaration):
            ntype = NodeType.INTERFACE
        elif isinstance(type_decl, javalang.tree.EnumDeclaration):
            ntype = NodeType.ENUM
        else:
            continue

        class_fqn = fqn(type_decl.name)
        class_id = f"java::{class_fqn}"
        extras: Dict[str, dict] = {"fields": {}}
        class_node = Node(
            id=class_id, type=ntype, name=type_decl.name, fqn=class_fqn, file=path,
            line=(type_decl.position.line if type_decl.position else None),
            modifiers=list(type_decl.modifiers or []),
            annotations=anno_list(type_decl.annotations), extras=extras,
        )
        nodes.append(class_node)
        edges.append(Edge(src=file_id, dst=class_id, type=EdgeType.CONTAINS))

        if getattr(type_decl, "extends", None):
            exts = type_decl.extends if isinstance(type_decl.extends, list) else [type_decl.extends]
            for e in exts:
                super_fqn = e.name if "." in e.name else fqn(e.name)
                super_id = f"java::{super_fqn}"
                nodes.append(Node(id=super_id, type=NodeType.CLASS, name=super_fqn.split('.')[-1], fqn=super_fqn))
                edges.append(Edge(src=class_id, dst=super_id, type=EdgeType.EXTENDS))

        if getattr(type_decl, "implements", None):
            for i in type_decl.implements or []:
                iface_fqn = i.name if "." in i.name else fqn(i.name)
                iface_id = f"java::{iface_fqn}"
                nodes.append(Node(id=iface_id, type=NodeType.INTERFACE, name=iface_fqn.split('.')[-1], fqn=iface_fqn))
                edges.append(Edge(src=class_id, dst=iface_id, type=EdgeType.IMPLEMENTS))

        # Fields
        for body_decl in type_decl.body:
            if isinstance(body_decl, javalang.tree.FieldDeclaration):
                field_type = getattr(body_decl.type, 'name', None)
                for declarator in body_decl.declarators or []:
                    fname = declarator.name
                    class_node.extras.setdefault("fields", {})[fname] = field_type

        # Methods & calls
        for body_decl in type_decl.body:
            if isinstance(body_decl, javalang.tree.MethodDeclaration):
                method_name = body_decl.name
                params = [{
                    "name": p.name, "type": (p.type.name if p.type else None),
                } for p in (body_decl.parameters or [])]
                return_type = body_decl.return_type.name if getattr(body_decl, "return_type", None) else None
                param_types = ",".join([p["type"] or "var" for p in params])
                method_fqn = f"{class_node.fqn}.{method_name}({param_types})"
                method_id = f"java::{method_fqn}"

                mnode = Node(
                    id=method_id, type=NodeType.METHOD, name=method_name, fqn=method_fqn,
                    file=path, line=(body_decl.position.line if body_decl.position else None),
                    modifiers=list(body_decl.modifiers or []), annotations=anno_list(body_decl.annotations),
                    params=params, returns=return_type,
                )
                nodes.append(mnode)
                edges.append(Edge(src=class_id, dst=method_id, type=EdgeType.CONTAINS))

                if body_decl.body:
                    for _, node2 in body_decl:
                        if isinstance(node2, javalang.tree.MethodInvocation):
                            callee_name = node2.member
                            qualifier = getattr(node2, "qualifier", None)
                            target_fqn_guess = f"{class_node.fqn}.{callee_name}"
                            callee_id = f"java::{target_fqn_guess}"
                            edges.append(Edge(
                                src=method_id, dst=callee_id, type=EdgeType.CALLS,
                                extras={"qualifier": qualifier, "package": package_name, "imports": imports},
                            ))

        for anno in class_node.annotations:
            edges.append(Edge(src=class_id, dst=f"anno::{anno}", type=EdgeType.ANNOTATED_BY))

    for imp in imports:
        edges.append(Edge(src=file_id, dst=f"import::{imp}", type=EdgeType.IMPORTS))

    return nodes, edges
