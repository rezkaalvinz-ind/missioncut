import pytest
from pydantic import ValidationError

from backend.demo import DEMO_GRAPH, DEMO_SCENARIOS
from backend.main import GraphPathRequest, app, demo, evaluate_scenario, graph_summary, report
from backend.models import CompareRequest, EvaluateRequest, GraphDocument
from backend.parsing import parse_graph


def test_health_and_openapi():
    assert app.openapi()["info"]["title"] == "MissionCut API"
    assert "/api/scenarios/compare" in app.openapi()["paths"]
    assert demo()["expected_independent_result"]["blocked_connection_count"] == 2


def test_api_demo_and_evaluate():
    payload = EvaluateRequest.model_validate(
        {"graph": DEMO_GRAPH.model_dump(), "scenario": DEMO_SCENARIOS[0].model_dump(), "sources": ["suspect"]}
    )
    assert evaluate_scenario(payload)["blocked_connection_count"] == 2


def test_api_invalid_graph_and_path():
    with pytest.raises(ValidationError):
        GraphDocument.model_validate({"nodes": [], "edges": [{"id": "e", "source": "a", "target": "b"}]})
    with pytest.raises(ValueError, match="does not exist"):
        from backend.main import paths

        paths(GraphPathRequest(graph=DEMO_GRAPH, source="missing", target="api"))


def test_csv_load_and_report():
    csv_data = (
        b"record_type,id,label,asset_type,criticality,source,target,status,change_cost\n"
        b"node,a,A,server,low,,,,\nnode,b,B,service,critical,,,,\nedge,ab,,,,a,b,active,1\n"
    )
    assert len(parse_graph(csv_data, "csv").edges) == 1
    assert graph_summary(DEMO_GRAPH)["nodes"] == 5
    body = CompareRequest.model_validate(
        {
            "graph": DEMO_GRAPH.model_dump(),
            "scenarios": [s.model_dump() for s in DEMO_SCENARIOS],
            "sources": ["suspect"],
        }
    )
    result = report(body)
    assert result["mode"] == "offline-simulation" and len(result["results"]) == 3


def test_api_evaluate_returns_actual_paths():
    payload = EvaluateRequest.model_validate(
        {"graph": DEMO_GRAPH.model_dump(), "scenario": DEMO_SCENARIOS[0].model_dump(), "sources": ["suspect"]}
    )
    result = evaluate_scenario(payload)
    before = result["paths_before"][0]
    assert "paths" in before
    assert sorted(tuple(p) for p in before["paths"]) == [("suspect", "api"), ("suspect", "jump", "api")]
    lost_paths = result["paths_lost"][0]["paths"]
    assert sorted(tuple(p) for p in lost_paths) == [("suspect", "api"), ("suspect", "jump", "api")]


def test_api_compare_baseline_isolation_vs_selective():
    """Full isolation is the baseline; selective should keep more services reachable."""
    from backend.main import compare_scenarios

    body = CompareRequest.model_validate(
        {
            "graph": DEMO_GRAPH.model_dump(),
            "scenarios": [DEMO_SCENARIOS[0].model_dump(), DEMO_SCENARIOS[1].model_dump()],
            "sources": ["suspect"],
        }
    )
    result = compare_scenarios(body)
    full = next(r for r in result["results"] if r["scenario"]["id"] == "isolate-suspect")
    selective = next(r for r in result["results"] if r["scenario"]["id"] == "block-direct")
    assert full["blocked_connection_count"] >= selective["blocked_connection_count"]
    assert selective["services_still_reachable"] >= full["services_still_reachable"]
    assert "block-direct" in result["recommendation"]["scenario_ids"]
