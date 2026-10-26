"""Offline graph analysis and isolated containment scenario evaluation."""

from __future__ import annotations

from itertools import islice

import networkx as nx

from .models import GraphDocument, Scenario

PATH_LIMIT = 500
MAX_PATH_PAIRS = 100


def build_graph(document: GraphDocument) -> nx.MultiDiGraph | nx.MultiGraph:
    graph = nx.MultiDiGraph() if document.directed else nx.MultiGraph()
    graph.graph.update(directed=document.directed, allow_parallel_edges=document.allow_parallel_edges)
    for node in document.nodes:
        graph.add_node(node.id, **node.model_dump())
    for edge in document.edges:
        graph.add_edge(edge.source, edge.target, key=edge.id, **edge.model_dump())
    return graph


def _simple_routes(graph, source: str, target: str, cap: int = PATH_LIMIT):
    """Return unique node-simple routes; parallel links do not inflate route count."""
    if source not in graph or target not in graph:
        return [], False
    view = nx.DiGraph() if graph.is_directed() else nx.Graph()
    view.add_nodes_from(graph.nodes)
    for u, v, _, data in graph.edges(keys=True, data=True):
        if data["status"] == "active":
            view.add_edge(u, v)
    iterator = nx.all_simple_paths(view, source, target, cutoff=max(0, len(view) - 1))
    routes = list(islice(iterator, cap + 1))
    truncated = len(routes) > cap
    return routes[:cap], truncated


def reachable_assets(graph, sources: list[str]) -> list[str]:
    active = nx.DiGraph() if graph.is_directed() else nx.Graph()
    active.add_nodes_from(graph.nodes)
    active.add_edges_from((u, v) for u, v, _, d in graph.edges(keys=True, data=True) if d["status"] == "active")
    reached = set()
    for source in sources:
        if source in active:
            reached.add(source)
            reached.update(
                nx.descendants(active, source) if active.is_directed() else nx.node_connected_component(active, source)
            )
    return sorted(reached)


def summary(document: GraphDocument) -> dict:
    return {
        "directed": document.directed,
        "nodes": len(document.nodes),
        "edges": len(document.edges),
        "active_connections": sum(e.status == "active" for e in document.edges),
        "blocked_connections": sum(e.status == "blocked" for e in document.edges),
        "critical_services": [{"id": n.id, "label": n.label} for n in document.nodes if n.criticality == "critical"],
        "allow_parallel_edges": document.allow_parallel_edges,
    }


def find_paths(document: GraphDocument, source: str, target: str, max_paths: int = 50) -> dict:
    graph = build_graph(document)
    if source not in graph or target not in graph:
        raise ValueError("Source or target node does not exist")
    routes, truncated = _simple_routes(graph, source, target, max_paths)
    return {"source": source, "target": target, "paths": routes, "count": len(routes), "truncated": truncated}


def _selected_edges(graph, scenario: Scenario) -> set[str]:
    known_nodes, known_edges = set(graph.nodes), {data["id"] for *_, data in graph.edges(keys=True, data=True)}
    unknown_nodes = set(scenario.suspect_node_ids) - known_nodes
    unknown_edges = set(scenario.edge_ids) - known_edges
    if unknown_nodes or unknown_edges:
        raise ValueError(f"Unknown selections: nodes={sorted(unknown_nodes)}, edges={sorted(unknown_edges)}")
    if scenario.kind in ("full_isolation", "custom"):
        return {
            data["id"]
            for u, v, key, data in graph.edges(keys=True, data=True)
            if u in scenario.suspect_node_ids or v in scenario.suspect_node_ids
        } | (set(scenario.edge_ids) if scenario.kind == "custom" else set())
    return set(scenario.edge_ids)


def evaluate(
    document: GraphDocument,
    scenario: Scenario,
    sources: list[str] | None = None,
    critical_targets: list[str] | None = None,
) -> dict:
    base = build_graph(document)
    selected = _selected_edges(base, scenario)
    # Each invocation gets an independent graph copy. The immutable GraphDocument is never modified.
    isolated = base.copy()
    before_critical = critical_targets or [n.id for n in document.nodes if n.criticality == "critical"]
    source_nodes = sources or scenario.suspect_node_ids
    unknown_sources = set(source_nodes) - set(base.nodes)
    unknown_targets = set(before_critical) - set(base.nodes)
    if unknown_sources or unknown_targets:
        raise ValueError(
            f"Unknown analysis nodes: sources={sorted(unknown_sources)}, targets={sorted(unknown_targets)}"
        )
    if len(source_nodes) * len(before_critical) > MAX_PATH_PAIRS:
        raise ValueError(f"Analysis is limited to {MAX_PATH_PAIRS} source-target pairs per scenario")
    for u, v, key, data in list(isolated.edges(keys=True, data=True)):
        if data["id"] in selected and data["status"] == "active":
            isolated[u][v][key]["status"] = "blocked"
    before_paths, after_paths, lost_paths = [], [], []
    truncated = False
    for source in source_nodes:
        for target in before_critical:
            before, t1 = _simple_routes(base, source, target)
            after, t2 = _simple_routes(isolated, source, target)
            truncated |= t1 or t2
            before_set = {tuple(p) for p in before}
            after_set = {tuple(p) for p in after}
            lost = [list(p) for p in before_set - after_set]
            remaining = [list(p) for p in after_set]
            before_paths.append({"source": source, "target": target, "count": len(before), "paths": before})
            after_paths.append({"source": source, "target": target, "count": len(after), "paths": remaining})
            lost_paths.append({"source": source, "target": target, "count": len(lost), "paths": lost})
    before_reach = set(reachable_assets(base, source_nodes))
    after_reach = set(reachable_assets(isolated, source_nodes))
    services = [
        {
            "id": target,
            "label": isolated.nodes[target]["label"],
            "reachable_before": target in before_reach,
            "reachable_after": target in after_reach,
        }
        for target in before_critical
        if target in isolated
    ]
    newly_blocked = [
        data
        for _, _, _, data in base.edges(keys=True, data=True)
        if data["id"] in selected and data["status"] == "active"
    ]
    changed_nodes = sorted({n for edge in newly_blocked for n in (edge["source"], edge["target"])})
    change_cost = sum(edge["change_cost"] or 0 for edge in newly_blocked)
    fully_unreachable = sum(s["reachable_before"] and not s["reachable_after"] for s in services)
    return {
        "scenario": scenario.model_dump(),
        "blocked_connection_count": len(newly_blocked),
        "changed_asset_count": len(changed_nodes),
        "change_cost": change_cost,
        "before_reachable_asset_count": len(before_reach),
        "after_reachable_asset_count": len(after_reach),
        "lost_reachable_asset_count": len(before_reach - after_reach),
        "paths_before": before_paths,
        "paths_after": after_paths,
        "paths_lost": lost_paths,
        "services": services,
        "services_still_reachable": sum(s["reachable_after"] for s in services),
        "services_unreachable_after": fully_unreachable,
        "path_counts_truncated": truncated,
        "assumptions": [
            "Routes are node-simple paths; parallel connections do not multiply the route count.",
            "A blocked connection cannot carry traffic in either modeled direction.",
            "No attack likelihood or real-world incident probability is inferred.",
        ],
    }


def compare(
    document: GraphDocument,
    scenarios: list[Scenario],
    sources: list[str] | None = None,
    critical_targets: list[str] | None = None,
) -> dict:
    results = [evaluate(document, s, sources, critical_targets) for s in scenarios]

    # Preserve reachability first, then minimize lost routes, changed links, and explicit cost.
    def score(result):
        return (
            -result["services_still_reachable"],
            sum(x["count"] for x in result["paths_lost"]),
            result["blocked_connection_count"],
            result["change_cost"],
        )

    best_score = min(map(score, results))
    winners = [r["scenario"]["id"] for r in results if score(r) == best_score]
    return {
        "results": results,
        "recommendation": {
            "scenario_ids": winners,
            "tie": len(winners) > 1,
            "criteria": [
                "Maximize critical services still reachable",
                "Minimize lost node-simple routes",
                "Minimize newly blocked connections",
                "Minimize sum of explicit change_cost",
            ],
            "trade_off": (
                "This prioritizes service continuity over containment breadth; operators must weigh "
                "mission needs and incident facts."
            ),
            "limitations": (
                "This is a transparent decision aid on supplied topology, not a prediction or "
                "automated containment command."
            ),
        },
    }
