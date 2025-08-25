from __future__ import annotations
from typing import List, Tuple, Dict, Any, Optional
from dataclasses import dataclass
from tree_sitter_languages import get_parser
from .graph_schema import Node, Edge, NodeType, EdgeType

# ============================================================
# Signature / runtime banner
# ============================================================
SIGNATURE = "java-parser-treesitter:ast-http-v1"
print(f"[CodeGraph] Loaded {SIGNATURE}")

# ============================================================
# HTTP mapping registry (centralized)
# ============================================================
_HTTP_MAP = {
    "@GetMapping": "GET",
    "@PostMapping": "POST",
    "@PutMapping": "PUT",
    "@DeleteMapping": "DELETE",
    "@PatchMapping": "PATCH",
}
_REQUEST_METHOD_PREFIX = "RequestMethod."

# ============================================================
# Utilities
# ============================================================
@dataclass
class TS:
    parser = get_parser("java")

def _text(src: bytes, node) -> str:
    return src[node.start_byte:node.end_byte].decode("utf-8")

def _dedup(xs: List[str]) -> List[str]:
    return [x for x in dict.fromkeys(xs) if str(x).strip() != ""]

def _join_paths(base: str, leaf: str) -> str:
    if not base and not leaf: return "/"
    if not base: return leaf if leaf.startswith("/") else f"/{leaf}"
    if not leaf: return base
    if base.endswith("/") and leaf.startswith("/"): return base[:-1] + leaf
    if not base.endswith("/") and not leaf.startswith("/"): return base + "/" + leaf
    return base + leaf

def _combine_paths(base_paths: List[str], method_paths: List[str]) -> List[str]:
    if base_paths and method_paths:
        out = [_join_paths(b, m) for b in base_paths for m in method_paths]
    elif method_paths:
        out = method_paths
    elif base_paths:
        out = base_paths
    else:
        out = []
    return _dedup(out)

# ============================================================
# Annotation extraction (Tree-sitter CST → our arg dict)
# ============================================================
def _string_lit_to_py(s: str) -> str:
    s = s.strip()
    if (len(s) >= 2) and ((s[0] == s[-1] == '"') or (s[0] == s[-1] == "'")):
        return s[1:-1]
    return s

def _elem_value_to_list(src: bytes, node) -> List[str]:
    """
    Convert an element_value node (or literal) to list[str].
    Handles:
      - string_literal
      - element_value_array_initializer -> { "a", "b" }
      - field_access (e.g., RequestMethod.GET) -> return as text
      - qualified_name / annotation / identifiers -> as text (best-effort)
    """
    t = node.type
    if t == "string_literal":
        return [_string_lit_to_py(_text(src, node))]
    if t == "element_value_array_initializer":
        vals = []
        for ch in node.children:
            if ch.type in ("string_literal", "character_literal", "decimal_integer_literal",
                           "decimal_floating_point_literal", "true", "false", "null_literal",
                           "field_access", "identifier", "scoped_identifier", "qualified_name", "element_value"):
                vals.extend(_elem_value_to_list(src, ch))
        return _dedup(vals)
    if t in ("character_literal", "decimal_integer_literal", "decimal_floating_point_literal",
             "true", "false", "null_literal"):
        return [_text(src, node)]
    if t in ("field_access", "identifier", "scoped_identifier", "qualified_name"):
        return [_text(src, node)]
    if t == "element_value":  # unwrap inner child
        for ch in node.children:
            return _elem_value_to_list(src, ch)
        return []
    # fallback to raw
    return [_text(src, node)]

def _parse_annotation_args(src: bytes, anno_node) -> Dict[str, Any]:
    """
    Returns dict with *_list variants and scalar convenience keys.
    Supports:
      - marker_annotation (no args)
      - normal annotation with annotation_argument_list
      - single-member: ( <element_value> )
      - pairs: ( k = <element_value>, ... )
    """
    out: Dict[str, Any] = {}

    arg_list = None
    for ch in anno_node.children:
        if ch.type == "annotation_argument_list":
            arg_list = ch
            break
        # For marker_annotation, there is no argument list.

    if arg_list is None:
        return out  # marker or empty

    # The children typically: '(' ... ')' with either element_value or element_value_pair(s)
    # Detect if we have pairs or a single element value.
    pairs = []
    single_value_node: Optional[object] = None

    for ch in arg_list.children:
        if ch.type == "element_value_pair":
            pairs.append(ch)
        elif ch.type == "element_value":
            single_value_node = ch

    if pairs:
        for p in pairs:
            # element_value_pair: identifier '=' element_value
            key_node = None
            val_node = None
            seen_eq = False
            for ch in p.children:
                if not seen_eq and ch.type == "identifier":
                    key_node = ch
                elif ch.type == "=":
                    seen_eq = True
                elif seen_eq:
                    val_node = ch
                    break
            if key_node is not None and val_node is not None:
                k = _text(src, key_node)
                vs = _elem_value_to_list(src, val_node)
                out[f"{k}_list"] = vs
                if vs:
                    out[k] = vs[0] if len(vs) == 1 else ",".join(vs)
        return out

    if single_value_node is not None:
        vs = _elem_value_to_list(src, single_value_node)
        out["value_list"] = vs
        if vs:
            out["value"] = vs[0] if len(vs) == 1 else ",".join(vs)
    return out

def _annotation_to_record(src: bytes, anno_node) -> Dict[str, Any]:
    """
    -> {"name":"@Anno", "full":"@Anno(...)", "args":{...}}
    """
    # structure: annotation: '@' identifier ('.' identifier)* annotation_argument_list?
    #            or marker_annotation variant (no args)
    name_ident_parts: List[str] = []
    args: Dict[str, Any] = {}

    # Find the qualified name after '@'
    after_at = False
    for ch in anno_node.children:
        if ch.type == "@":
            after_at = True
            continue
        if not after_at:
            continue
        # qualified_name can be a chain of identifiers with dots, but TS often gives identifiers/dots separately
        if ch.type in ("identifier", "scoped_identifier", "qualified_name"):
            name_ident_parts.append(_text(src, ch))
        if ch.type == "annotation_argument_list":
            args = _parse_annotation_args(src, anno_node)
            break

    # If no name captured yet, try a direct text slice (fallback)
    name = "@" + ("".join(name_ident_parts).strip() or _text(src, anno_node).split("(")[0].strip().lstrip("@"))

    # Full text display
    full = name
    if args:
        parts = []
        if "value_list" in args and args["value_list"]:
            parts.append(", ".join(args["value_list"]))
        for key in ("path", "consumes", "produces", "params", "headers", "name", "method"):
            lst_key = f"{key}_list"
            if lst_key in args and args[lst_key]:
                parts.append(f"{key}=" + ", ".join(args[lst_key]))
            elif key in args and args[key]:
                parts.append(f"{key}={args[key]}")
        if parts:
            full = f"{name}({', '.join(parts)})"

    return {"name": name, "full": full, "args": args}

# ============================================================
# HTTP extraction identical to javalang version (consumes *_list)
# ============================================================
def _extract_http_basic(anno_ds: List[Dict[str, Any]]) -> Dict[str, Any]:
    methods: List[str] = []
    paths: List[str] = []
    consumes: List[str] = []
    produces: List[str] = []
    params: List[str] = []
    headers: List[str] = []
    name: Optional[str] = None

    for d in anno_ds:
        nm, args = d["name"], (d.get("args") or {})

        # Shortcut annotations
        if nm in _HTTP_MAP:
            methods.append(_HTTP_MAP[nm])
            for key in ("value_list", "path_list"):
                if args.get(key):
                    paths.extend(args[key])
            if args.get("consumes_list"): consumes.extend(args["consumes_list"])
            if args.get("produces_list"): produces.extend(args["produces_list"])
            if args.get("params_list"):   params.extend(args["params_list"])
            if args.get("headers_list"):  headers.extend(args["headers_list"])
            if args.get("name"):          name = args["name"]

        # @RequestMapping
        if nm == "@RequestMapping":
            mlist = args.get("method_list") or []
            for item in mlist:
                if item.startswith(_REQUEST_METHOD_PREFIX):
                    methods.append(item[len(_REQUEST_METHOD_PREFIX):])

            for key in ("value_list", "path_list"):
                if args.get(key):
                    paths.extend(args[key])

            if args.get("consumes_list"): consumes.extend(args["consumes_list"])
            if args.get("produces_list"): produces.extend(args["produces_list"])
            if args.get("params_list"):   params.extend(args["params_list"])
            if args.get("headers_list"):  headers.extend(args["headers_list"])
            if args.get("name"):          name = args["name"]

    return {
        "methods":  _dedup(methods),
        "paths":    _dedup(paths),
        "consumes": _dedup(consumes),
        "produces": _dedup(produces),
        "params":   _dedup(params),
        "headers":  _dedup(headers),
        "name": name,
    }

def _extract_response_status(anno_ds: List[Dict[str, Any]]) -> Optional[str]:
    for d in anno_ds:
        if d["name"] == "@ResponseStatus":
            args = d.get("args") or {}
            return args.get("value") or args.get("code")
    return None

def _extract_cors(anno_ds: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    for d in anno_ds:
        if d["name"] == "@CrossOrigin":
            args = d.get("args") or {}
            cors: Dict[str, Any] = {}
            for k in ("origins", "allowedHeaders", "exposedHeaders", "methods", "maxAge", "allowCredentials"):
                lst = args.get(f"{k}_list")
                if lst: cors[k] = lst
                elif args.get(k): cors[k] = [args[k]] if k != "maxAge" else args[k]
            return cors or None
    return None

# ============================================================
# Parameter sources via TS (from formal parameters)
# ============================================================
def _extract_param_sources_ts(src: bytes, method_node) -> Dict[str, Any]:
    param_sources = []
    path_vars, query_params, header_params, body_params, cookie_params = [], [], [], [], []

    # find formal_parameters node
    formals = None
    for ch in method_node.children:
        if ch.type == "formal_parameters":
            formals = ch
            break

    if formals is None:
        return {
            "param_sources": [],
            "path_variables": [], "query_params": [], "header_params": [],
            "body_params": [], "cookie_params": []
        }

    # Each formal_parameter can have modifiers containing annotations
    for idx, p in enumerate([c for c in formals.children if c.type in ("formal_parameter", "receiver_parameter")]):
        pname = None
        ptype = None
        annos = []

        # Collect pieces
        for ch in p.children:
            if ch.type == "variable_declarator_id" or ch.type == "identifier":
                pname = _text(src, ch).split("[", 1)[0]
            elif ch.type in ("type_identifier", "integral_type", "floating_point_type", "boolean_type", "void_type",
                             "scoped_type_identifier", "generic_type", "array_type", "qualified_name"):
                ptype = _text(src, ch)
            elif ch.type == "modifiers":
                for m in ch.children:
                    if m.type in ("annotation", "marker_annotation", "annotation"):
                        annos.append(m)

        info = {"index": idx, "name": pname, "type": ptype, "source": "unknown", "required": None, "default": None}

        # Parse param annotations
        for a in annos:
            rec = _annotation_to_record(src, a)
            nm, args = rec["name"], rec["args"]
            if nm == "@PathVariable":
                lst = args.get("value_list") or args.get("name_list") or []
                var = lst[0] if lst else (args.get("value") or args.get("name") or pname)
                info.update({"source": "path", "name": var})
                path_vars.append(var)
            elif nm == "@RequestParam":
                lst = args.get("value_list") or args.get("name_list") or []
                qp = lst[0] if lst else (args.get("value") or args.get("name") or pname)
                req = args.get("required")
                info.update({"source": "query", "name": qp, "required": None if req is None else (str(req).lower()=="true"),
                             "default": args.get("defaultValue")})
                query_params.append(qp)
            elif nm == "@RequestHeader":
                lst = args.get("value_list") or args.get("name_list") or []
                hn = lst[0] if lst else (args.get("value") or args.get("name") or pname)
                req = args.get("required")
                info.update({"source": "header", "name": hn, "required": None if req is None else (str(req).lower()=="true"),
                             "default": args.get("defaultValue")})
                header_params.append(hn)
            elif nm == "@RequestBody":
                req = args.get("required")
                info.update({"source": "body", "required": None if req is None else (str(req).lower()=="true")})
                body_params.append(pname)
            elif nm == "@RequestPart":
                lst = args.get("value_list") or args.get("name_list") or []
                part = lst[0] if lst else (args.get("value") or args.get("name") or pname)
                req = args.get("required")
                info.update({"source": "part", "name": part, "required": None if req is None else (str(req).lower()=="true")})
            elif nm == "@CookieValue":
                lst = args.get("value_list") or args.get("name_list") or []
                ck = lst[0] if lst else (args.get("value") or args.get("name") or pname)
                req = args.get("required")
                info.update({"source": "cookie", "name": ck, "required": None if req is None else (str(req).lower()=="true"),
                             "default": args.get("defaultValue")})
                cookie_params.append(ck)

        param_sources.append(info)

    return {
        "param_sources": param_sources,
        "path_variables": _dedup(path_vars),
        "query_params": _dedup(query_params),
        "header_params": _dedup(header_params),
        "body_params": _dedup(body_params),
        "cookie_params": _dedup(cookie_params),
    }

# ============================================================
# Main parser (Tree-sitter)
# ============================================================
def parse_java_source_ts(src: str, path: str) -> Tuple[List[Node], List[Edge]]:
    """
    Tree-sitter based Java parser that mirrors the javalang-based output.
    """
    parser = TS.parser
    source_bytes = src.encode("utf-8")
    tree = parser.parse(source_bytes)
    root = tree.root_node

    nodes: List[Node] = []
    edges: List[Edge] = []

    file_id = f"file::{path}"
    nodes.append(Node(id=file_id, type=NodeType.FILE, name=path.split("/")[-1], fqn=path, file=path))

    # Package/imports (best-effort)
    package_name: Optional[str] = None
    imports: List[str] = []

    for ch in root.children:
        if ch.type == "package_declaration":
            # package_declaration: 'package' scoped_identifier ';'
            for c2 in ch.children:
                if c2.type in ("scoped_identifier", "identifier", "qualified_name"):
                    package_name = _text(source_bytes, c2)
                    break
        elif ch.type == "import_declaration":
            imports.append(_text(source_bytes, ch).replace("import", "").replace("static", "").replace(";", "").strip())

    def fqn(name: str) -> str:
        return f"{package_name}.{name}" if package_name else name

    # Walk top-level type declarations
    for td in [c for c in root.children if c.type in ("class_declaration", "interface_declaration", "enum_declaration")]:

        # Name & kind
        tname = None
        for c2 in td.children:
            if c2.type == "identifier":
                tname = _text(source_bytes, c2)
                break
        if not tname:
            continue

        kind = td.type
        if   kind == "class_declaration":     ntype = NodeType.CLASS
        elif kind == "interface_declaration": ntype = NodeType.INTERFACE
        else:                                 ntype = NodeType.ENUM

        class_fqn = fqn(tname)
        class_id = f"java::{class_fqn}"

        # Class annotations
        class_annos_nodes = []
        # annotations live under a preceding 'modifiers' node, or inline in td.children (depending on grammar versions)
        # Collect modifiers anywhere directly under the declaration
        for c2 in td.children:
            if c2.type == "modifiers":
                for m in c2.children:
                    if m.type in ("annotation", "marker_annotation"):
                        class_annos_nodes.append(m)

        class_annos = [_annotation_to_record(source_bytes, a) for a in class_annos_nodes]
        class_http_raw = _extract_http_basic(class_annos)

        class_node = Node(
            id=class_id,
            type=ntype,
            name=tname,
            fqn=class_fqn,
            file=path,
            line=(td.start_point[0] + 1),
            modifiers=[],  # could populate by scanning 'modifiers'
            annotations=[d["name"] for d in class_annos],
            extras={
                "fields": {},
                "annotation_texts": [d["full"] for d in class_annos],
                "annotation_args":  [d["args"] for d in class_annos],
                "http": class_http_raw if any(class_http_raw.values()) else None,
            },
        )
        nodes.append(class_node)
        edges.append(Edge(src=file_id, dst=class_id, type=EdgeType.CONTAINS))

        # Extends / Implements
        for c2 in td.children:
            if c2.type == "superclass":
                for si in c2.children:
                    if si.type in ("type_identifier", "scoped_type_identifier", "qualified_name", "identifier"):
                        super_name = _text(source_bytes, si)
                        super_fqn = super_name if "." in super_name else fqn(super_name)
                        super_id = f"java::{super_fqn}"
                        nodes.append(Node(id=super_id, type=NodeType.CLASS, name=super_fqn.split(".")[-1], fqn=super_fqn))
                        edges.append(Edge(src=class_id, dst=super_id, type=EdgeType.EXTENDS))
            if c2.type == "super_interfaces":
                for si in c2.children:
                    if si.type in ("type_identifier", "scoped_type_identifier", "qualified_name", "identifier"):
                        iface_name = _text(source_bytes, si)
                        iface_fqn = iface_name if "." in iface_name else fqn(iface_name)
                        iface_id = f"java::{iface_fqn}"
                        nodes.append(Node(id=iface_id, type=NodeType.INTERFACE, name=iface_fqn.split(".")[-1], fqn=iface_fqn))
                        edges.append(Edge(src=class_id, dst=iface_id, type=EdgeType.IMPLEMENTS))

        # Fields (lightweight)
        body = None
        for c2 in td.children:
            if c2.type == "class_body" or c2.type == "interface_body" or c2.type == "enum_body":
                body = c2
                break

        if body is None:
            continue

        for member in body.children:
            # Fields
            if member.type == "field_declaration":
                ftype = None
                fname = None
                for ch in member.children:
                    if ch.type in ("type_identifier", "integral_type", "floating_point_type", "boolean_type",
                                   "scoped_type_identifier", "generic_type", "array_type", "qualified_name"):
                        ftype = _text(source_bytes, ch)
                    if ch.type == "variable_declarator":
                        for leaf in ch.children:
                            if leaf.type == "identifier":
                                fname = _text(source_bytes, leaf)
                                class_node.extras.setdefault("fields", {})[fname] = ftype

            # Methods
            if member.type == "method_declaration":
                method_name = None
                return_type = None
                for ch in member.children:
                    if ch.type == "identifier":
                        method_name = _text(source_bytes, ch)
                    elif ch.type in ("type_identifier", "integral_type", "floating_point_type", "boolean_type",
                                     "scoped_type_identifier", "generic_type", "array_type", "void_type", "qualified_name"):
                        # The first such node before params is the return type
                        if return_type is None:
                            return_type = _text(source_bytes, ch)

                # Params (names/types)
                params: List[Dict[str, str]] = []
                formals = None
                for ch in member.children:
                    if ch.type == "formal_parameters":
                        formals = ch
                        break
                if formals:
                    for p in [c for c in formals.children if c.type in ("formal_parameter", "receiver_parameter")]:
                        pname, ptype = None, None
                        for leaf in p.children:
                            if leaf.type == "variable_declarator_id" or leaf.type == "identifier":
                                pname = _text(source_bytes, leaf).split("[", 1)[0]
                            elif leaf.type in ("type_identifier", "integral_type", "floating_point_type", "boolean_type",
                                               "scoped_type_identifier", "generic_type", "array_type", "qualified_name"):
                                ptype = _text(source_bytes, leaf)
                        params.append({"name": pname, "type": ptype})

                param_types = ",".join([(x.get("type") or "var") for x in params])
                method_fqn = f"{class_node.fqn}.{method_name}({param_types})"
                method_id = f"java::{method_fqn}"

                # Method annotations (from modifiers)
                method_annos_nodes = []
                for ch in member.children:
                    if ch.type == "modifiers":
                        for m in ch.children:
                            if m.type in ("annotation", "marker_annotation"):
                                method_annos_nodes.append(m)
                m_annos = [_annotation_to_record(source_bytes, a) for a in method_annos_nodes]

                # HTTP info
                method_http_raw = _extract_http_basic(m_annos)
                response_status = _extract_response_status(m_annos)
                cors            = _extract_cors(m_annos)
                param_meta      = _extract_param_sources_ts(source_bytes, member)

                # Base paths from class
                base_paths        = (class_http_raw.get("paths")    if class_http_raw else [])
                class_methods     = (class_http_raw.get("methods")  if class_http_raw else [])
                class_consumes    = (class_http_raw.get("consumes") if class_http_raw else [])
                class_produces    = (class_http_raw.get("produces") if class_http_raw else [])
                class_params      = (class_http_raw.get("params")   if class_http_raw else [])
                class_headers     = (class_http_raw.get("headers")  if class_http_raw else [])
                class_name        = (class_http_raw.get("name")     if class_http_raw else None)

                method_paths = method_http_raw.get("paths", [])
                combined_paths = _combine_paths(base_paths, method_paths)
                effective_methods  = method_http_raw.get("methods")  or class_methods
                effective_consumes = method_http_raw.get("consumes") or class_consumes
                effective_produces = method_http_raw.get("produces") or class_produces
                effective_params   = _dedup([*class_params,  *method_http_raw.get("params", [])])
                effective_headers  = _dedup([*class_headers, *method_http_raw.get("headers", [])])
                effective_name     = method_http_raw.get("name") or class_name

                mnode = Node(
                    id=method_id,
                    type=NodeType.METHOD,
                    name=method_name,
                    fqn=method_fqn,
                    file=path,
                    line=(member.start_point[0] + 1),
                    modifiers=[],  # could collect from 'modifiers'
                    annotations=[d["name"] for d in m_annos],
                    params=params,
                    returns=return_type,
                    extras={
                        "annotation_texts": [d["full"] for d in m_annos],
                        "annotation_args":  [d["args"] for d in m_annos],
                        "http": {
                            "methods":        effective_methods,
                            "paths":          method_paths,
                            "base_paths":     base_paths,
                            "combined_paths": combined_paths,
                            "consumes":       effective_consumes,
                            "produces":       effective_produces,
                            "params":         effective_params,
                            "headers":        effective_headers,
                            "name":           effective_name,
                            "raw":            {"class": class_http_raw, "method": method_http_raw},
                            "response_status": response_status,
                            "cors":            cors,
                            **param_meta,
                            "path_variables_in_combined": [
                                pv for pv in param_meta.get("path_variables", [])
                                if any(f"{{{pv}}}" in (p or "") for p in combined_paths)
                            ],
                        },
                    },
                )
                nodes.append(mnode)
                edges.append(Edge(src=class_id, dst=method_id, type=EdgeType.CONTAINS))

                # Naive CALL edges (very light best-effort): scan for method_invocation nodes
                # Tree-sitter Java names them 'method_invocation'
                def _walk(n):
                    if n.type == "method_invocation":
                        # member + (optional) object: object.member(...)
                        callee_name = None
                        qual = None
                        for ch in n.children:
                            if ch.type == "identifier" and callee_name is None:
                                callee_name = _text(source_bytes, ch)
                            if ch.type in ("field_access", "scoped_identifier", "identifier"):
                                # not perfect; capture some qualifier text
                                q = _text(source_bytes, ch)
                                if "." in q:
                                    qual = q.rsplit(".", 1)[0]
                        if callee_name:
                            guess = f"{class_node.fqn}.{callee_name}"
                            edges.append(Edge(
                                src=method_id, dst=f"java::{guess}", type=EdgeType.CALLS,
                                extras={"qualifier": qual, "package": package_name, "imports": imports}
                            ))
                    for ch in n.children:
                        _walk(ch)
                _walk(member)

        # Class annotation edges
        for anno_name in class_node.annotations or []:
            edges.append(Edge(src=class_id, dst=f"anno::{anno_name}", type=EdgeType.ANNOTATED_BY))

    # File import edges
    for imp in imports:
        edges.append(Edge(src=file_id, dst=f"import::{imp}", type=EdgeType.IMPORTS))

    return nodes, edges
