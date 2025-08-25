
# CodeGraph Inline Bundle

## Install
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

## Run example
```bash
python -m inline_agentkit.run_example
```
# After rebuilding the graph G
from codegraph.query_engine import dynamic_query

# 1) Your example path is now captured
res = dynamic_query(G, {"kind":"method","http_method_any":["GET"],"http_path_regex":r"/updatingProduct/\\{productId\\}", "neighbors":0}).to_json()
print(res["nodes"][0]["extras"]["http"])

# 2) All endpoints that produce JSON
dynamic_query(G, {"kind":"method","http_produces_any":["application/json"]}).to_json()

# 3) Endpoints with any path variables
dynamic_query(G, {"kind":"method","http_has_path_vars": True}).to_json()

