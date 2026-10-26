"""Validated graph and scenario schemas for MissionCut."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_NODES = 250
MAX_EDGES = 1_000


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AssetNode(StrictModel):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_.:-]+$")
    label: str = Field(min_length=1, max_length=120)
    asset_type: Literal["endpoint", "server", "database", "identity", "network", "cloud", "service"]
    criticality: Literal["critical", "high", "medium", "low"] = "medium"


class Connection(StrictModel):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_.:-]+$")
    source: str = Field(min_length=1, max_length=80)
    target: str = Field(min_length=1, max_length=80)
    status: Literal["active", "blocked"] = "active"
    change_cost: float | None = Field(default=None, ge=0, le=1_000_000)
    label: str = Field(default="", max_length=120)


class GraphDocument(StrictModel):
    directed: bool = True
    allow_parallel_edges: bool = True
    nodes: list[AssetNode] = Field(max_length=MAX_NODES)
    edges: list[Connection] = Field(max_length=MAX_EDGES)

    @model_validator(mode="after")
    def validate_graph(self):
        node_ids = [node.id for node in self.nodes]
        edge_ids = [edge.id for edge in self.edges]
        if len(set(node_ids)) != len(node_ids):
            raise ValueError("Node IDs must be unique")
        if len(set(edge_ids)) != len(edge_ids):
            raise ValueError("Edge IDs must be unique")
        known = set(node_ids)
        for edge in self.edges:
            if edge.source not in known or edge.target not in known:
                raise ValueError(f"Edge {edge.id} refers to an unknown node")
        pairs = [
            (edge.source, edge.target) if self.directed else tuple(sorted((edge.source, edge.target)))
            for edge in self.edges
        ]
        if not self.allow_parallel_edges and len(set(pairs)) != len(pairs):
            raise ValueError("Parallel edges are disabled but a node pair is repeated")
        return self


class Scenario(StrictModel):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_.:-]+$")
    name: str = Field(min_length=1, max_length=120)
    kind: Literal["full_isolation", "selective", "custom"]
    suspect_node_ids: list[str] = Field(default_factory=list, max_length=MAX_NODES)
    edge_ids: list[str] = Field(default_factory=list, max_length=MAX_EDGES)

    @model_validator(mode="after")
    def unique_selections(self):
        if len(self.suspect_node_ids) != len(set(self.suspect_node_ids)):
            raise ValueError("suspect_node_ids must not contain duplicates")
        if len(self.edge_ids) != len(set(self.edge_ids)):
            raise ValueError("edge_ids must not contain duplicates")
        if self.kind == "selective" and not self.edge_ids:
            raise ValueError("Selective containment requires at least one edge_id")
        if self.kind == "full_isolation" and not self.suspect_node_ids:
            raise ValueError("Full isolation requires at least one suspect node")
        return self


class PathRequest(StrictModel):
    source: str
    target: str
    max_paths: int = Field(default=50, ge=1, le=500)


class EvaluateRequest(StrictModel):
    graph: GraphDocument
    scenario: Scenario
    sources: list[str] = Field(default_factory=list, max_length=MAX_NODES)
    critical_targets: list[str] = Field(default_factory=list, max_length=MAX_NODES)


class CompareRequest(StrictModel):
    graph: GraphDocument
    scenarios: list[Scenario] = Field(min_length=1, max_length=20)
    sources: list[str] = Field(default_factory=list, max_length=MAX_NODES)
    critical_targets: list[str] = Field(default_factory=list, max_length=MAX_NODES)
