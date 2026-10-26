import pytest
from pydantic import ValidationError

from backend.demo import DEMO_GRAPH, DEMO_SCENARIOS, EXPECTED_DEMO
from backend.engine import build_graph, compare, evaluate, find_paths, reachable_assets
from backend.models import GraphDocument, Scenario


def graph(nodes, edges, directed=True, parallel=True):
    return GraphDocument.model_validate(
        {"directed": directed, "allow_parallel_edges": parallel, "nodes": nodes, "edges": edges}
    )


def node(id, criticality="low"):
    return {"id": id, "label": id, "asset_type": "server", "criticality": criticality}


def edge(id, source, target, status="active", cost=None):
    result = {"id": id, "source": source, "target": target, "status": status}
    if cost is not None:
        result["change_cost"] = cost
    return result


def test_empty_graph_and_single_node():
    empty = graph([], [])
    assert build_graph(empty).number_of_nodes() == 0
    one = graph([node("one", "critical")], [])
    assert find_paths(one, "one", "one")["count"] == 1
    result = evaluate(one, Scenario(id="none", name="No-op", kind="custom"), sources=["one"])
    assert result["services_still_reachable"] == 1


def test_graph_size_limit_is_enforced():
    with pytest.raises(ValidationError):
        graph([node(f"n{i}") for i in range(251)], [])


def test_multiple_routes_and_manual_expected_result():
    result = evaluate(DEMO_GRAPH, DEMO_SCENARIOS[0], sources=["suspect"])
    assert result["blocked_connection_count"] == EXPECTED_DEMO["blocked_connection_count"]
    assert result["changed_asset_count"] == EXPECTED_DEMO["changed_asset_count"]
    assert result["paths_before"][0]["count"] == 2
    assert result["paths_after"][0]["count"] == 0
    assert result["services_still_reachable"] == EXPECTED_DEMO["services_still_reachable"]


def test_no_path_and_blocked_link():
    g = graph([node("a"), node("b", "critical")], [edge("ab", "a", "b", "blocked")])
    assert find_paths(g, "a", "b")["count"] == 0
    assert reachable_assets(build_graph(g), ["a"]) == ["a"]


def test_selective_containment_keeps_alternate_route():
    g = graph(
        [node("a"), node("b"), node("c", "critical")],
        [edge("ab", "a", "b"), edge("bc", "b", "c"), edge("ac", "a", "c")],
    )
    scenario = Scenario(id="select", name="Selective", kind="selective", edge_ids=["ac"])
    result = evaluate(g, scenario, sources=["a"])
    assert result["paths_before"][0]["count"] == 2
    assert result["paths_after"][0]["count"] == 1
    assert result["services_still_reachable"] == 1


def test_full_isolation_device_with_multiple_paths():
    result = evaluate(DEMO_GRAPH, DEMO_SCENARIOS[0], sources=["suspect"])
    assert result["blocked_connection_count"] == 2
    assert result["paths_lost"][0]["count"] == 2


def test_base_graph_and_scenarios_do_not_mutate_each_other():
    before = DEMO_GRAPH.model_dump()
    evaluate(DEMO_GRAPH, DEMO_SCENARIOS[0], sources=["suspect"])
    evaluate(DEMO_GRAPH, DEMO_SCENARIOS[1], sources=["suspect"])
    assert DEMO_GRAPH.model_dump() == before
    assert DEMO_GRAPH.edges[0].status == "active"


def test_parallel_edges_do_not_inflate_asset_routes_but_changes_are_counted():
    g = graph([node("a"), node("b", "critical")], [edge("ab1", "a", "b"), edge("ab2", "a", "b")])
    assert find_paths(g, "a", "b")["count"] == 1
    result = evaluate(g, Scenario(id="c", name="custom", kind="custom", edge_ids=["ab1", "ab2"]), sources=["a"])
    assert result["blocked_connection_count"] == 2
    assert result["services_still_reachable"] == 0


def test_undirected_routes():
    g = graph([node("a"), node("b", "critical")], [edge("ab", "a", "b")], directed=False)
    assert find_paths(g, "b", "a")["paths"] == [["b", "a"]]


@pytest.mark.parametrize(
    "nodes,edges",
    [
        ([node("a"), node("a")], []),
        ([node("a")], [edge("missing", "a", "x")]),
        ([node("a"), node("b")], [edge("e1", "a", "b"), edge("e1", "a", "b")]),
        ([node("a"), node("b")], [edge("e1", "a", "b"), edge("e2", "a", "b")]),
    ],
)
def test_invalid_duplicate_or_disallowed_connections(nodes, edges):
    parallel = False if len(edges) == 2 else True
    with pytest.raises(ValidationError):
        graph(nodes, edges, parallel=parallel)


def test_unknown_scenario_selection_is_rejected():
    with pytest.raises(ValueError, match="Unknown selections"):
        evaluate(DEMO_GRAPH, Scenario(id="x", name="x", kind="custom", edge_ids=["does-not-exist"]))


def test_comparison_reports_tie_and_transparent_criteria():
    s1 = Scenario(id="a", name="A", kind="custom")
    s2 = Scenario(id="b", name="B", kind="custom")
    result = compare(DEMO_GRAPH, [s1, s2], sources=["suspect"])
    assert result["recommendation"]["tie"] is True
    assert result["recommendation"]["scenario_ids"] == ["a", "b"]
    assert result["recommendation"]["criteria"]


def test_demo_expected_is_independent_of_runtime_output():
    # Hand-check: suspect→api and suspect→jump→api; e1/e2 remove both, cost 2+3.
    result = evaluate(DEMO_GRAPH, DEMO_SCENARIOS[0], sources=["suspect"])
    assert (result["paths_before"][0]["count"], result["paths_after"][0]["count"], result["change_cost"]) == (2, 0, 5)


def test_selective_vs_full_isolation_baseline_comparison():
    """Compare selective containment against the full-isolation baseline."""
    full = evaluate(DEMO_GRAPH, DEMO_SCENARIOS[0], sources=["suspect"])
    selective = evaluate(DEMO_GRAPH, DEMO_SCENARIOS[1], sources=["suspect"])
    # Full isolation blocks more connections than selective
    assert full["blocked_connection_count"] >= selective["blocked_connection_count"]
    # Selective keeps at least as many critical services reachable
    assert selective["services_still_reachable"] >= full["services_still_reachable"]
    # Compare should recommend the option that retains more services
    result = compare(DEMO_GRAPH, [DEMO_SCENARIOS[0], DEMO_SCENARIOS[1]], sources=["suspect"])
    recommended = result["recommendation"]["scenario_ids"]
    assert "block-direct" in recommended


def test_evaluate_returns_actual_paths_not_just_counts():
    """Verify that evaluation includes actual route sequences, not just counts."""
    result = evaluate(DEMO_GRAPH, DEMO_SCENARIOS[0], sources=["suspect"])
    before = result["paths_before"][0]
    after = result["paths_after"][0]
    lost = result["paths_lost"][0]
    # paths_before should contain actual route lists (order may vary)
    assert "paths" in before
    assert sorted(tuple(p) for p in before["paths"]) == [("suspect", "api"), ("suspect", "jump", "api")]
    # paths_after should be empty (all routes cut by full isolation)
    assert after["paths"] == []
    # paths_lost should contain the routes that were present before but not after
    assert sorted(tuple(p) for p in lost["paths"]) == [("suspect", "api"), ("suspect", "jump", "api")]


def test_selective_keeps_remaining_paths_visible():
    """When selective containment blocks one route, the remaining route is shown."""
    g = graph(
        [node("a"), node("b"), node("c", "critical")],
        [edge("ab", "a", "b"), edge("bc", "b", "c"), edge("ac", "a", "c")],
    )
    scenario = Scenario(id="select", name="Selective", kind="selective", edge_ids=["ac"])
    result = evaluate(g, scenario, sources=["a"])
    # Before: a→c and a→b→c (2 routes, order may vary)
    assert sorted(tuple(p) for p in result["paths_before"][0]["paths"]) == [("a", "b", "c"), ("a", "c")]
    # After: only a→b→c remains
    assert result["paths_after"][0]["paths"] == [["a", "b", "c"]]
    # Lost: the direct a→c route
    assert result["paths_lost"][0]["paths"] == [["a", "c"]]
