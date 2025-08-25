from __future__ import annotations
from typing import List, Tuple, Dict, Any
import javalang
from .graph_schema import Node, Edge, NodeType, EdgeType


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
# AST value normalization helpers (pure AST, no regex)
# ============================================================

def _val_to_str(v) -> str:
    if isinstance(v, str):
        t = v.strip()
        if (t.startswith('"') and t.endswith('"')) or (t.startswith("'") and t.endswith("'")):
            return t[1:-1]
        return t
    if isinstance(v, (int, float, bool)):
        return str(v)

    s = getattr(v, "value", None)
    if s is not None:
        return _val_to_str(s)

    member = getattr(v, "member", None)
    qualifier = getattr(v, "qualifier", None)
    if member is not None or qualifier is not None:
        return f"{qualifier + '.' if qualifier else ''}{member or ''}" or str(v)

    name = getattr(v, "name", None)
    if name:
        return f"@{name}"

    return str(v)


def _val_to_list(v) -> List[str]:
    if v is None:
        return []
    if hasattr(v, "values") and getattr(v, "values", None) is not None:
        return [_val_to_str(x) for x in v.values]
    if isinstance(v, (list, tuple)):
        return [_val_to_str(x) for x in v]
    s = _val_to_str(v)
    return [s] if s else []

# ============================================================
# Annotation extraction
# ============================================================

def _anno_kv(a) -> dict:
    out: dict = {}

    if hasattr(a, "value") and a.value is not None:
        vs = _val_to_list(a.value)
        out["value_list"] = vs
        if vs: out["value"] = vs[0] if len(vs) == 1 else ",".join(vs)
        return out

    if hasattr(a, "member") and a.member is not None:
        vs = _val_to_list(a.member)
        out["value_list"] = vs
        if vs: out["value"] = vs[0] if len(vs) == 1 else ",".join(vs)
        return out

    elems = getattr(a, "element", None)
    if elems is not None:
        if isinstance(elems, (list, tuple)):
            for p in elems:
                k = getattr(p, "name", None)
                v = getattr(p, "value", None)
                vs = _val_to_list(v)
                if k and vs:
                    out[k] = vs[0] if len(vs) == 1 else ",".join(vs)
                    out[f"{k}_list"] = vs
        else:
            nfield = getattr(elems, "name", None)
            vfield = getattr(elems, "value", None)
            vs = _val_to_list(vfield)
            if nfield:
                out[nfield] = vs[0] if len(vs) == 1 else ",".join(vs)
                out[f"{nfield}_list"] = vs
            else:
                out["value_list"] = vs
                if vs: out["value"] = vs[0] if len(vs) == 1 else ",".join(vs)
        return out

    return out


def _anno_details(a) -> dict:
    name = f"@{getattr(a, 'name', 'Unknown')}"
    args = _anno_kv(a)

    if args:
        parts = []
        if "value_list" in args and args["value_list"]:
            parts.append(", ".join(args["value_list"]))
        for key in ("path", "consumes", "produces", "params", "headers", "name", "method"):
            if f"{key}_list" in args and args[f"{key}_list"]:
                parts.append(f"{key}={', '.join(args[f'{key}_list'])}")
            elif key in args and args[key]:
                parts.append(f"{key}={args[key]}")
        full = f"{name}({', '.join(parts)})" if parts else name
    else:
        full = name

    return {"name": name, "full": full, "args": args}

# ============================================================
# HTTP extraction
# ============================================================

def _dedup(xs: list[str]) -> list[str]:
    return [x for x in dict.fromkeys(xs) if str(x).strip() != ""]


def _extract_http_basic(anno_ds: list[dict]) -> dict:
    methods: list[str] = []
    paths: list[str] = []
    consumes: list[str] = []
    produces: list[str] = []
    params: list[str] = []
    headers: list[str] = []
    name: str | None = None

    for d in anno_ds:
        nm, args = d["name"], (d.get("args") or {})

        if nm in _HTTP_MAP:
            methods.append(_HTTP_MAP[nm])
            for key in ("value_list", "path_list"):
                if key in args and args[key]:
                    paths.extend(args[key])
            if "consumes_list" in args: consumes.extend(args["consumes_list"])
            if "produces_list" in args: produces.extend(args["produces_list"])
            if "params_list" in args:   params.extend(args["params_list"])
            if "headers_list" in args:  headers.extend(args["headers_list"])
            if "name" in args and args["name"]: name = args["name"]

        if nm == "@RequestMapping":
            mlist = args.get("method_list") or []
            for item in mlist:
                if item.startswith(_REQUEST_METHOD_PREFIX):
                    methods.append(item[len(_REQUEST_METHOD_PREFIX):])
            for key in ("value_list", "path_list"):
                if key in args and args[key]:
                    paths.extend(args[key])
            if "consumes_list" in args: consumes.extend(args["consumes_list"])
            if "produces_list" in args: produces.extend(args["produces_list"])
            if "params_list" in args:   params.extend(args["params_list"])
            if "headers_list" in args:  headers.extend(args["headers_list"])
            if "name" in args and args["name"]: name = args["name"]

    return {
        "methods":  _dedup(methods),
        "paths":    _dedup(paths),
        "consumes": _dedup(consumes),
        "produces": _dedup(produces),
        "params":   _dedup(params),
        "headers":  _dedup(headers),
        "name": name,
    }
# ============================================================
# HTTP path composition
# ============================================================

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
# Parameter sources (path/query/header/body/cookie/part)
# ============================================================

def _parse_bool(s: str | None) -> bool | None:
    if s is None: return None
    ls = str(s).lower()
    if ls in ("true", "false"): return ls == "true"
    return None


def _extract_param_sources(method_decl) -> Dict[str, Any]:
    param_sources = []
    path_vars = []
    query_params = []
    header_params = []
    body_params = []
    cookie_params = []

    for idx, p in enumerate(getattr(method_decl, 'parameters', None) or []):
        ptype = getattr(getattr(p, 'type', None), 'name', None)
        pname = getattr(p, 'name', None)
        annos = getattr(p, 'annotations', None) or []
        info = {"index": idx, "name": pname, "type": ptype, "source": "unknown", "required": None, "default": None}

        def args_of(a): return _anno_kv(a)

        for a in annos:
            nm = f"@{getattr(a, 'name', 'Unknown')}"
            kwargs = args_of(a)
            if nm == "@PathVariable":
                var = kwargs.get("value_list", []) or kwargs.get("name_list", [])
                var_name = (var[0] if var else (kwargs.get("value") or kwargs.get("name") or pname))
                info.update({"source": "path", "name": var_name})
                path_vars.append(var_name)
            elif nm == "@RequestParam":
                lst = kwargs.get("value_list", []) or kwargs.get("name_list", [])
                qp = (lst[0] if lst else (kwargs.get("value") or kwargs.get("name") or pname))
                req = _parse_bool(kwargs.get("required"))
                info.update({"source": "query", "name": qp, "required": req, "default": kwargs.get("defaultValue")})
                query_params.append(qp)
            elif nm == "@RequestHeader":
                lst = kwargs.get("value_list", []) or kwargs.get("name_list", [])
                hn = (lst[0] if lst else (kwargs.get("value") or kwargs.get("name") or pname))
                req = _parse_bool(kwargs.get("required"))
                info.update({"source": "header", "name": hn, "required": req, "default": kwargs.get("defaultValue")})
                header_params.append(hn)
            elif nm == "@RequestBody":
                req = _parse_bool(kwargs.get("required"))
                info.update({"source": "body", "required": req})
                body_params.append(pname)
            elif nm == "@RequestPart":
                lst = kwargs.get("value_list", []) or kwargs.get("name_list", [])
                part = (lst[0] if lst else (kwargs.get("value") or kwargs.get("name") or pname))
                req = _parse_bool(kwargs.get("required"))
                info.update({"source": "part", "name": part, "required": req})
            elif nm == "@CookieValue":
                lst = kwargs.get("value_list", []) or kwargs.get("name_list", [])
                ck = (lst[0] if lst else (kwargs.get("value") or kwargs.get("name") or pname))
                req = _parse_bool(kwargs.get("required"))
                info.update({"source": "cookie", "name": ck, "required": req, "default": kwargs.get("defaultValue")})
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
# Response status & CORS (AST-based)
# ============================================================

def _extract_response_status(anno_ds: List[Dict[str, Any]]) -> str | None:
    for d in anno_ds:
        if d["name"] == "@ResponseStatus":
            args = d.get("args") or {}
            # Could be 'value' or 'code' (enum like HttpStatus.OK)
            return args.get("value") or args.get("code")
    return None


def _extract_cors(anno_ds: List[Dict[str, Any]]) -> Dict[str, Any] | None:
    for d in anno_ds:
        if d["name"] == "@CrossOrigin":
            args = d.get("args") or {}
            cors: Dict[str, Any] = {}
            for k in ("origins", "allowedHeaders", "exposedHeaders", "methods", "maxAge", "allowCredentials"):
                list_key = f"{k}_list"
                if list_key in args and args[list_key]:
                    cors[k] = args[list_key]
                elif k in args and args[k]:
                    cors[k] = [args[k]] if k != "maxAge" else args[k]
            return cors or None
    return None

# ============================================================
# Main parser
# ============================================================

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

    for type_decl in tree.types:
        kind = getattr(type_decl, "__class__", type("x",(),{})).__name__
        if   kind == "ClassDeclaration":     ntype = NodeType.CLASS
        elif kind == "InterfaceDeclaration": ntype = NodeType.INTERFACE
        elif kind == "EnumDeclaration":      ntype = NodeType.ENUM
        else: continue

        class_fqn = fqn(type_decl.name)
        class_id = f"java::{class_fqn}"

        # ----- Class annotations + base HTTP -----
        class_annos = [_anno_details(a) for a in (getattr(type_decl, 'annotations', None) or [])]
        class_http_raw = _extract_http_basic(class_annos)

        class_node = Node(
            id=class_id,
            type=ntype,
            name=type_decl.name,
            fqn=class_fqn,
            file=path,
            line=(type_decl.position.line if getattr(type_decl, 'position', None) else None),
            modifiers=list(getattr(type_decl, 'modifiers', None) or []),
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

        # Inheritance
        exts = getattr(type_decl, "extends", None)
        if exts is not None:
            exts_list = exts if isinstance(exts,(list,tuple)) else [exts]
            for e in exts_list:
                en = getattr(e,"name",None)
                if en:
                    super_fqn = en if "." in en else fqn(en)
                    super_id = f"java::{super_fqn}"
                    nodes.append(Node(id=super_id, type=NodeType.CLASS, name=super_fqn.split('.')[-1], fqn=super_fqn))
                    edges.append(Edge(src=class_id, dst=super_id, type=EdgeType.EXTENDS))

        impls = getattr(type_decl, "implements", None)
        if impls is not None:
            for i in impls:
                iname = getattr(i,"name",None)
                if iname:
                    iface_fqn = iname if "." in iname else fqn(iname)
                    iface_id = f"java::{iface_fqn}"
                    nodes.append(Node(id=iface_id, type=NodeType.INTERFACE, name=iface_fqn.split('.')[-1], fqn=iface_fqn))
                    edges.append(Edge(src=class_id, dst=iface_id, type=EdgeType.IMPLEMENTS))

        # Fields (for naive call resolution)
        for body_decl in getattr(type_decl, "body", []) or []:
            if getattr(body_decl, "__class__", type("x",(),{})).__name__ == "FieldDeclaration":
                ftype = getattr(getattr(body_decl,'type',None), 'name', None)
                for dec in getattr(body_decl,'declarators',None) or []:
                    fname = getattr(dec,'name',None)
                    if fname: class_node.extras.setdefault("fields",{})[fname] = ftype

        # ----- Methods -----
        base_paths        = (class_http_raw.get("paths")    if class_http_raw else [])
        class_methods     = (class_http_raw.get("methods")  if class_http_raw else [])
        class_consumes    = (class_http_raw.get("consumes") if class_http_raw else [])
        class_produces    = (class_http_raw.get("produces") if class_http_raw else [])
        class_params      = (class_http_raw.get("params")   if class_http_raw else [])
        class_headers     = (class_http_raw.get("headers")  if class_http_raw else [])
        class_name        = (class_http_raw.get("name")     if class_http_raw else None)

        for body_decl in getattr(type_decl, "body", []) or []:
            if getattr(body_decl, "__class__", type("x",(),{})).__name__ != "MethodDeclaration":
                continue

            method_name = getattr(body_decl,'name',None)
            params = []
            for p in getattr(body_decl,'parameters',None) or []:
                params.append({
                    "name": getattr(p,'name',None),
                    "type": getattr(getattr(p,'type',None),'name',None),
                })
            return_type = getattr(getattr(body_decl,'return_type',None),'name',None)
            param_types = ",".join([(x.get("type") or "var") for x in params])
            method_fqn = f"{class_node.fqn}.{method_name}({param_types})"
            method_id  = f"java::{method_fqn}"

            m_annos = [_anno_details(a) for a in (getattr(body_decl,'annotations',None) or [])]
            method_http_raw = _extract_http_basic(m_annos)
            response_status = _extract_response_status(m_annos)
            cors = _extract_cors(m_annos)
            param_meta = _extract_param_sources(body_decl)

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
                line=(getattr(body_decl,'position',None).line if getattr(body_decl,'position',None) else None),
                modifiers=list(getattr(body_decl,'modifiers',None) or []),
                annotations=[d["name"] for d in m_annos],
                params=params,
                returns=return_type,
                extras={
                    "annotation_texts": [d["full"] for d in m_annos],
                    "annotation_args":  [d["args"] for d in m_annos],
                    "http": {
                        "methods":       effective_methods,
                        "paths":         method_paths,
                        "base_paths":    base_paths,
                        "combined_paths": combined_paths,
                        "consumes":      effective_consumes,
                        "produces":      effective_produces,
                        "params":        effective_params,
                        "headers":       effective_headers,
                        "name":          effective_name,
                        "raw":           {"class": class_http_raw, "method": method_http_raw},
                        "response_status": response_status,
                        "cors":            cors,
                        **param_meta,
                        # convenient derived info:
                        "path_variables_in_combined": [
                            pv for pv in param_meta.get("path_variables", [])
                            if any(f"{{{pv}}}" in (p or "") for p in combined_paths)
                        ],
                    },
                },
            )
            nodes.append(mnode)
            edges.append(Edge(src=class_id, dst=method_id, type=EdgeType.CONTAINS))

            # Naive call graph edges (best-effort)
            if getattr(body_decl,'body',None):
                for _, n2 in body_decl:
                    if getattr(n2, "__class__", type("x",(),{})).__name__ == "MethodInvocation":
                        callee = getattr(n2,'member',None)
                        qual   = getattr(n2,'qualifier',None)
                        if not callee: continue
                        guess = f"{class_node.fqn}.{callee}"
                        edges.append(Edge(
                            src=method_id, dst=f"java::{guess}", type=EdgeType.CALLS,
                            extras={"qualifier": qual, "package": package_name, "imports": imports}
                        ))

        # annotate class with its annotation names
        for anno in class_node.annotations or []:
            edges.append(Edge(src=class_id, dst=f"anno::{anno}", type=EdgeType.ANNOTATED_BY))

    # file-level imports
    for imp in imports:
        edges.append(Edge(src=file_id, dst=f"import::{imp}", type=EdgeType.IMPORTS))

    return nodes, edges
