# Architecture and algorithm notes

MissionCut separates input validation, graph calculation, API transport, and presentation. Pydantic rejects unknown schema fields and invalid graph references. FastAPI applies request validation and stable JSON error responses. NetworkX MultiGraph/MultiDiGraph models directedness and independent parallel links.

## System architecture

```mermaid
flowchart TD
    subgraph Frontend["Frontend (Next.js + TypeScript)"]
        UI["page.tsx<br/>SVG graph visualization<br/>Scenario builder<br/>Comparison dashboard"]
        API_CLIENT["Fetch client<br/>→ Backend REST API"]
    end

    subgraph Backend["Backend (Python + FastAPI)"]
        API["main.py<br/>REST endpoints + error handling"]
        PARSER["parsing.py<br/>JSON / CSV loader"]
        MODELS["models.py<br/>Pydantic schemas<br/>(strict, extra=forbid)"]
        ENGINE["engine.py<br/>NetworkX graph operations"]
        DEMO["demo.py<br/>Synthetic topology<br/>+ independent expected result"]
    end

    subgraph Data["Data"]
        JSON["datasets/sample-graph.json"]
        CSV["datasets/sample-graph.csv"]
    end

    UI --> API_CLIENT
    API_CLIENT -->|"HTTP /api/*"| API
    API --> PARSER --> MODELS
    API --> ENGINE --> MODELS
    API --> DEMO --> ENGINE
    DEMO --> MODELS
    JSON -.->|"demo / upload"| PARSER
    CSV -.->|"upload"| PARSER
```

## Request flow

```mermaid
sequenceDiagram
    participant U as User (Browser)
    participant F as Frontend (Next.js)
    participant A as API (FastAPI)
    participant E as Engine (NetworkX)
    participant M as Models (Pydantic)

    U->>F: Load demo / upload graph
    F->>A: GET /api/demo or POST /api/graphs/load
    A->>M: Validate graph (strict schema)
    M-->>A: GraphDocument
    A-->>F: Graph + summary

    U->>F: Select suspect + scenario type
    U->>F: Click "Compare containment options"
    F->>A: POST /api/scenarios/compare
    A->>M: Validate scenarios
    M-->>A: Scenario objects
    A->>E: compare(graph, scenarios)
    loop Each scenario (1-20)
        E->>E: Copy graph, block edges
        E->>E: Enumerate before/after routes
        E->>E: Compute reachability + metrics
    end
    E-->>A: Results + lexicographic recommendation
    A-->>F: Comparison JSON
    F->>U: Display cards, paths, recommendation
```

## Algorithm details

For reachability and route enumeration, the engine builds an active simple-graph projection from active edges. `networkx.all_simple_paths` enumerates node-simple routes up to a hard cap; using a simple projection keeps multi-edge links from inflating route counts. The graph has at most 250 assets and 1,000 links; analysis allows at most 100 source-target pairs and 500 routes for each pair. This bounds response work while acknowledging that route enumeration is combinatorial.

Containment selection is mapped to edge IDs. Full isolation selects every link incident to a suspect asset, selective containment selects the supplied edge IDs, and custom containment unions the links incident to selected assets with explicitly selected edges. Evaluation copies the NetworkX graph and changes statuses only on that copy. The base Pydantic document is read-only to the evaluator.

Before/after output separates route counts per source/target pair, assets reachable from selected sources, critical-service reachability, links newly blocked, distinct endpoint assets affected by those links, and explicit change cost. Routes lost are the nonnegative difference of bounded before and after counts; when a cap is hit, `path_counts_truncated` signals that these may be lower bounds. Each path entry also includes the actual route node sequences so the frontend can display which specific paths were cut and which remain.

The recommendation comparator uses deterministic lexicographic sorting: maximize reachable critical services, then minimize routes lost, newly blocked links, and explicit cost. Identical tuples produce a tie. It does not use weights or probabilities.

All data is in-memory and synthetic demo data ships with the repo. The frontend only renders and requests backend evaluations; it does not carry a separate scoring implementation. Reports include a simulation disclaimer.
