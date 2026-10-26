"""Synthetic training topology and independently calculated expected result."""

from .engine import evaluate
from .models import GraphDocument, Scenario

DEMO_GRAPH = GraphDocument.model_validate(
    {
        "directed": True,
        "allow_parallel_edges": True,
        "nodes": [
            {"id": "suspect", "label": "Suspected workstation", "asset_type": "endpoint", "criticality": "low"},
            {"id": "jump", "label": "Admin jump host", "asset_type": "server", "criticality": "high"},
            {"id": "api", "label": "Customer API", "asset_type": "service", "criticality": "critical"},
            {"id": "db", "label": "Customer database", "asset_type": "database", "criticality": "critical"},
            {"id": "backup", "label": "Read replica", "asset_type": "database", "criticality": "critical"},
        ],
        "edges": [
            {"id": "e1", "source": "suspect", "target": "jump", "status": "active", "change_cost": 2},
            {"id": "e2", "source": "suspect", "target": "api", "status": "active", "change_cost": 3},
            {"id": "e3", "source": "jump", "target": "api", "status": "active", "change_cost": 1},
            {"id": "e4", "source": "api", "target": "db", "status": "active", "change_cost": 1},
            {"id": "e5", "source": "backup", "target": "db", "status": "active", "change_cost": 1},
            {"id": "e6", "source": "jump", "target": "backup", "status": "blocked", "change_cost": 1},
        ],
    }
)

DEMO_SCENARIOS = [
    Scenario(
        id="isolate-suspect", name="Isolate suspected workstation", kind="full_isolation", suspect_node_ids=["suspect"]
    ),
    Scenario(id="block-direct", name="Block direct workstation to API", kind="selective", edge_ids=["e2"]),
    Scenario(
        id="block-both",
        name="Block both workstation exits",
        kind="custom",
        suspect_node_ids=["suspect"],
        edge_ids=["e3"],
    ),
]

# Independent manual result for the first scenario: suspect has exactly two node-simple paths to api
# (suspect→api and suspect→jump→api), none to db/backup. Isolating its two incident links removes both.
EXPECTED_DEMO = {
    "scenario_id": "isolate-suspect",
    "blocked_connection_count": 2,
    "changed_asset_count": 3,
    "services_still_reachable": 0,
    "services_unreachable_after": 2,
    "paths_before_to_api": 2,
    "paths_after_to_api": 0,
    "services": ["api", "db", "backup"],
}


def demo_results():
    return {
        "graph": DEMO_GRAPH,
        "scenarios": DEMO_SCENARIOS,
        "expected_independent_result": EXPECTED_DEMO,
        "evaluations": [evaluate(DEMO_GRAPH, s, sources=["suspect"]) for s in DEMO_SCENARIOS],
    }
