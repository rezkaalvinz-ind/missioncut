# MissionCut API Contract

Base URL: `http://localhost:8000` (configurable). OpenAPI interactive docs at `/docs`.

All endpoints except `/api/graphs/load` accept and return JSON. Errors return a stable `error` object:

```json
{"error": {"code": "invalid_input", "message": "descriptive message"}}
```

| Code | HTTP Status | Cause |
|------|-------------|-------|
| `validation_error` | 422 | Request body fails schema validation |
| `invalid_input` | 400 | Semantic error (unknown node, dangling edge, limit exceeded) |
| `input_too_large` | 413 | Request body exceeds 1 MB |

## Limits

- Request body: 1 MB
- Graph: 250 nodes, 1,000 edges
- Path request: 500 routes maximum
- Scenario analysis: 100 source-target pairs, 500 routes per pair

---

## GET /api/health

Health check.

**Response 200:**
```json
{"status": "ok", "mode": "offline-simulation"}
```

---

## GET /api/demo

Returns the synthetic demo graph, three pre-configured scenarios, an independently hand-verified expected result, and full evaluations for each scenario.

**Response 200:**
```json
{
  "graph": { /* GraphDocument */ },
  "scenarios": [ /* Scenario[] */ ],
  "expected_independent_result": {
    "scenario_id": "isolate-suspect",
    "blocked_connection_count": 2,
    "changed_asset_count": 3,
    "services_still_reachable": 0,
    "services_unreachable_after": 2,
    "paths_before_to_api": 2,
    "paths_after_to_api": 0,
    "services": ["api", "db", "backup"]
  },
  "evaluations": [ /* Evaluation[] */ ]
}
```

---

## POST /api/graphs/validate

Validate a JSON graph body without persisting it.

**Request body:** `GraphDocument`

```json
{
  "directed": true,
  "allow_parallel_edges": true,
  "nodes": [
    {"id": "suspect", "label": "Suspected workstation", "asset_type": "endpoint", "criticality": "low"}
  ],
  "edges": [
    {"id": "e1", "source": "suspect", "target": "jump", "status": "active", "change_cost": 2}
  ]
}
```

**Response 200:**
```json
{"valid": true, "summary": { /* see Summary */ }, "graph": { /* GraphDocument */ }}
```

**Response 422:** Validation error with field-level details.

---

## POST /api/graphs/load?format=json|csv

Parse a raw JSON or CSV upload. The body is the raw file content (not JSON-wrapped).

**Query parameter:** `format` — `json` or `csv`

**Request body:** Raw bytes (UTF-8). For CSV, the header must be:
`record_type,id,label,asset_type,criticality,source,target,status,change_cost`

**Response 200:**
```json
{"valid": true, "summary": { /* see Summary */ }, "graph": { /* GraphDocument */ }}
```

---

## POST /api/graphs/summary

Compute graph statistics.

**Request body:** `GraphDocument`

**Response 200 (Summary):**
```json
{
  "directed": true,
  "nodes": 5,
  "edges": 6,
  "active_connections": 5,
  "blocked_connections": 1,
  "critical_services": [{"id": "api", "label": "Customer API"}],
  "allow_parallel_edges": true
}
```

---

## POST /api/paths

Find active node-simple routes between two nodes.

**Request body:**
```json
{
  "graph": { /* GraphDocument */ },
  "source": "suspect",
  "target": "api",
  "max_paths": 50
}
```

**Response 200:**
```json
{
  "source": "suspect",
  "target": "api",
  "paths": [["suspect", "api"], ["suspect", "jump", "api"]],
  "count": 2,
  "truncated": false
}
```

`truncated` is `true` when the route count reached the safety cap (default 500); reported counts may be lower bounds.

---

## POST /api/scenarios/evaluate

Evaluate a single containment scenario on a private graph copy.

**Request body (EvaluateRequest):**
```json
{
  "graph": { /* GraphDocument */ },
  "scenario": {
    "id": "isolate-suspect",
    "name": "Isolate suspected workstation",
    "kind": "full_isolation",
    "suspect_node_ids": ["suspect"],
    "edge_ids": []
  },
  "sources": ["suspect"],
  "critical_targets": []
}
```

`sources` defaults to `scenario.suspect_node_ids`. `critical_targets` defaults to all nodes with `criticality: "critical"`.

**Response 200 (Evaluation):**
```json
{
  "scenario": { /* Scenario */ },
  "blocked_connection_count": 2,
  "changed_asset_count": 3,
  "change_cost": 5,
  "before_reachable_asset_count": 4,
  "after_reachable_asset_count": 1,
  "lost_reachable_asset_count": 3,
  "paths_before": [
    {"source": "suspect", "target": "api", "count": 2, "paths": [["suspect","api"],["suspect","jump","api"]]}
  ],
  "paths_after": [
    {"source": "suspect", "target": "api", "count": 0, "paths": []}
  ],
  "paths_lost": [
    {"source": "suspect", "target": "api", "count": 2, "paths": [["suspect","api"],["suspect","jump","api"]]}
  ],
  "services": [
    {"id": "api", "label": "Customer API", "reachable_before": true, "reachable_after": false}
  ],
  "services_still_reachable": 0,
  "services_unreachable_after": 2,
  "path_counts_truncated": false,
  "assumptions": [
    "Routes are node-simple paths; parallel connections do not multiply the route count.",
    "A blocked connection cannot carry traffic in either modeled direction.",
    "No attack likelihood or real-world incident probability is inferred."
  ]
}
```

Each entry in `paths_before`, `paths_after`, and `paths_lost` now includes the actual route sequences in the `paths` field, not just a `count`. `paths_lost` contains routes that existed before but not after; `paths_after` contains only routes that remain.

---

## POST /api/scenarios/compare

Compare 1 to 20 scenarios and return a lexicographic recommendation.

**Request body (CompareRequest):**
```json
{
  "graph": { /* GraphDocument */ },
  "scenarios": [ /* Scenario[] (1-20) */ ],
  "sources": ["suspect"],
  "critical_targets": []
}
```

**Response 200:**
```json
{
  "results": [ /* Evaluation[] */ ],
  "recommendation": {
    "scenario_ids": ["block-direct"],
    "tie": false,
    "criteria": [
      "Maximize critical services still reachable",
      "Minimize lost node-simple routes",
      "Minimize newly blocked connections",
      "Minimize sum of explicit change_cost"
    ],
    "trade_off": "This prioritizes service continuity over containment breadth; operators must weigh mission needs and incident facts.",
    "limitations": "This is a transparent decision aid on supplied topology, not a prediction or automated containment command."
  }
}
```

Ranking is lexicographic: (1) maximize critical services still reachable, (2) minimize routes lost, (3) minimize newly blocked links, (4) minimize explicit change cost. Exact ties are returned as ties.

---

## POST /api/reports

Produce a backend-generated comparison report with a simulation disclaimer.

**Request body:** `CompareRequest`

**Response 200:**
```json
{
  "title": "MissionCut containment comparison",
  "mode": "offline-simulation",
  "graph_summary": { /* Summary */ },
  "results": [ /* Evaluation[] */ ],
  "recommendation": { /* see Compare */ },
  "disclaimer": "Based only on the supplied topology and rules. Not a real-world incident prediction or a command to contain production systems."
}
```

---

## Data Models

### AssetNode
| Field | Type | Required | Default | Constraints |
|-------|------|----------|---------|-------------|
| `id` | string | yes | — | 1-80 chars, `^[A-Za-z0-9_.:-]+$`, unique |
| `label` | string | yes | — | 1-120 chars |
| `asset_type` | enum | yes | — | `endpoint`, `server`, `database`, `identity`, `network`, `cloud`, `service` |
| `criticality` | enum | no | `medium` | `critical`, `high`, `medium`, `low` |

### Connection (Edge)
| Field | Type | Required | Default | Constraints |
|-------|------|----------|---------|-------------|
| `id` | string | yes | — | 1-80 chars, `^[A-Za-z0-9_.:-]+$`, unique |
| `source` | string | yes | — | must reference an existing node |
| `target` | string | yes | — | must reference an existing node |
| `status` | enum | no | `active` | `active`, `blocked` |
| `change_cost` | float\|null | no | `null` | 0 to 1,000,000 |
| `label` | string | no | `""` | max 120 chars |

### Scenario
| Field | Type | Required | Default | Constraints |
|-------|------|----------|---------|-------------|
| `id` | string | yes | — | 1-80 chars, `^[A-Za-z0-9_.:-]+$` |
| `name` | string | yes | — | 1-120 chars |
| `kind` | enum | yes | — | `full_isolation`, `selective`, `custom` |
| `suspect_node_ids` | string[] | no | `[]` | max 250, no duplicates |
| `edge_ids` | string[] | no | `[]` | max 1000, no duplicates |

Validation rules:
- `selective` requires at least one `edge_id`
- `full_isolation` requires at least one `suspect_node_id`
- `custom` may use both; all referenced nodes and edges must exist in the graph
