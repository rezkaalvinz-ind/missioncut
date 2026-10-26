"""Strict JSON and CSV graph loaders. CSV uses nodes.csv and edges.csv with documented columns."""

import csv
import io
import json

from pydantic import ValidationError

from .models import GraphDocument

MAX_UPLOAD_BYTES = 1_000_000


def parse_graph(payload: bytes, format: str) -> GraphDocument:
    if len(payload) > MAX_UPLOAD_BYTES:
        raise ValueError("Input exceeds the 1 MB limit")
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("Input must be UTF-8") from exc
    if format == "json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON at line {exc.lineno}, column {exc.colno}") from exc
    elif format == "csv":
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
        allowed = {
            "record_type",
            "id",
            "label",
            "asset_type",
            "criticality",
            "source",
            "target",
            "status",
            "change_cost",
        }
        if reader.fieldnames is None or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError("CSV header is missing or contains duplicate columns")
        unsupported = set(reader.fieldnames) - allowed
        if unsupported:
            raise ValueError(f"Unsupported CSV columns: {', '.join(sorted(unsupported))}")
        if not rows or not {"record_type", "id"}.issubset(rows[0]):
            raise ValueError("CSV requires record_type and id columns")
        nodes, edges = [], []
        for row in rows:
            if None in row:
                raise ValueError("CSV row has more values than the header")
            kind = row.pop("record_type", "").strip()
            row = {k: v for k, v in row.items() if v not in (None, "")}
            if kind == "node":
                if {"source", "target", "status", "change_cost"} & row.keys():
                    raise ValueError("CSV node row contains edge-only fields")
                nodes.append(
                    {
                        "id": row.get("id"),
                        "label": row.get("label", row.get("id")),
                        "asset_type": row.get("asset_type", "server"),
                        "criticality": row.get("criticality", "medium"),
                    }
                )
            elif kind == "edge":
                if {"asset_type", "criticality"} & row.keys():
                    raise ValueError("CSV edge row contains node-only fields")
                edge = {
                    "id": row.get("id"),
                    "source": row.get("source"),
                    "target": row.get("target"),
                    "status": row.get("status", "active"),
                    "label": row.get("label", ""),
                }
                if "change_cost" in row:
                    try:
                        edge["change_cost"] = float(row["change_cost"])
                    except ValueError as exc:
                        raise ValueError(f"CSV edge {row.get('id')} has invalid change_cost") from exc
                edges.append(edge)
            else:
                raise ValueError("CSV record_type must be 'node' or 'edge'")
        data = {"directed": True, "allow_parallel_edges": True, "nodes": nodes, "edges": edges}
    else:
        raise ValueError("format must be json or csv")
    if not isinstance(data, dict):
        raise ValueError("Graph document must be a JSON object")
    try:
        return GraphDocument.model_validate(data)
    except ValidationError as exc:
        messages = "; ".join(error["msg"] for error in exc.errors()[:5])
        raise ValueError(f"Invalid graph document: {messages}") from exc
