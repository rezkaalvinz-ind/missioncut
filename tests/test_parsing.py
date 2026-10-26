import pytest
from pydantic import ValidationError

from backend.parsing import parse_graph

JSON = (
    b'{"directed":true,"allow_parallel_edges":false,"nodes":[{"id":"a","label":"A","asset_type":"server"}],"edges":[]}'
)


def test_json_parser():
    assert parse_graph(JSON, "json").nodes[0].id == "a"


def test_csv_parser():
    raw = (
        b"record_type,id,label,asset_type,criticality,source,target,status,change_cost\n"
        b"node,a,A,server,low,,,,\nnode,b,B,service,critical,,,,\nedge,e1,,,,a,b,active,1.5\n"
    )
    graph = parse_graph(raw, "csv")
    assert len(graph.nodes) == 2 and graph.edges[0].change_cost == 1.5


@pytest.mark.parametrize("raw,fmt", [(b"{oops", "json"), (b"record_type,id\nweird,x\n", "csv"), (b"x", "xml")])
def test_bad_input(raw, fmt):
    with pytest.raises((ValueError, ValidationError)):
        parse_graph(raw, fmt)


def test_oversized_input():
    with pytest.raises(ValueError, match="1 MB"):
        parse_graph(b"x" * 1_000_001, "json")


def test_unsupported_fields_are_rejected():
    raw = b'{"nodes":[],"edges":[],"surprise":true}'
    with pytest.raises(ValueError, match="Invalid graph document"):
        parse_graph(raw, "json")
