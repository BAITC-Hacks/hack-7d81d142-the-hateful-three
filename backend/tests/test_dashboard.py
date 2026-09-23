"""Integration of archive import, analysis, dashboard APIs, and CSV contracts."""

import csv
from datetime import date
from io import BytesIO, StringIO
from zipfile import ZipFile

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from backend.services.exceptions import ValidationError


def archive_bytes(tables):
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        for name, rows in tables.items():
            file = BytesIO()
            pq.write_table(pa.Table.from_pylist(rows), file)
            archive.writestr(f"data/{name}.parquet", file.getvalue())
    return output.getvalue()


@pytest.fixture
def tables():
    gids = [100000000343175100 + i for i in range(27)]
    nodes = [{"gid": gid, "depth": min(i, 4) if i < 5 else (0 if i == 26 else 1),
              "is_seed": i in (0, 26)} for i, gid in enumerate(gids)]
    edges, transactions = [], []
    for i in range(1, 26):
        src, dst = gids[i - 1] if i < 5 else gids[0], gids[i]
        count = 2 if i == 1 else 1
        edges.append(dict(src=src, dst=dst, sum_kzt=10.0 * count, n_tx=count, depth=min(i, 4) if i < 5 else 1))
        transactions.extend(dict(src=src, dst=dst, sum_kzt=10.0, date=date(2026, 7, 1)) for _ in range(count))
    return {"nodes": nodes, "edges": edges, "transactions": transactions}


def upload(client, tables):
    return client.post("/dataset/import", files={"file": ("data.zip", archive_bytes(tables), "application/zip")})


@pytest.fixture
def imported(client, tables):
    response = upload(client, tables)
    assert response.status_code == 201, response.text
    return response.json()


def test_dashboard_and_assets_public_api_stays_protected(client):
    client.headers.pop("Authorization")
    assert client.get("/").status_code == 200
    assert '/static/app.js' in client.get("/").text
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/styles.css").status_code == 200
    for path in ["/dataset", "/graph", "/graph/nodes/123", "/ranking/search", "/exports/nodes_roles.csv"]:
        assert client.get(path).status_code == 401
    assert client.post("/analysis").status_code == 401
    assert client.post("/dataset/import", files={"file": ("bad.zip", b"bad")}).status_code == 401


def test_empty_dataset_and_analysis(client):
    assert client.get("/dataset").json()["nodes"] == 0
    assert client.get("/graph").json()["nodes"] == []
    assert client.get("/ranking/search").json()["total"] == 0
    assert client.post("/analysis").status_code == 422
    assert client.get("/graph/nodes/missing").status_code == 404


def test_import_summary_precise_gids_duplicates_and_boundary(client, imported, tables):
    assert imported["nodes"] == 27
    assert imported["transactions"] == 26  # Identical source transfers are retained.
    assert imported["edges"] == 25
    assert imported["seeds"] == 2
    assert imported["truncated_nodes"] == 1
    assert imported["analysis_ready"] is True
    assert sum(imported["role_counts"].values()) == 27
    gid = str(tables["nodes"][4]["gid"])
    node = client.get(f"/graph/nodes/{gid}").json()
    assert node["gid"] == gid
    assert node["role"] == "peripheral"
    assert node["truncated_by_depth"] is True
    assert "не подтверждён" in node["evidence"]
    isolate = client.get(f'/graph/nodes/{tables["nodes"][26]["gid"]}').json()
    assert isolate["priority_score"] == 0
    assert isolate["in_deg"] == isolate["out_deg"] == 0


def test_search_pagination_sort_and_cluster_filters(client, imported, tables):
    first = client.get("/ranking/search?limit=10").json()
    second = client.get("/ranking/search?limit=10&skip=10").json()
    assert first["total"] == 27
    assert len(first["items"]) == len(second["items"]) == 10
    assert {n["gid"] for n in first["items"]}.isdisjoint(n["gid"] for n in second["items"])
    assert [n["rank"] for n in first["items"]] == list(range(1, 11))
    all_rows = client.get("/ranking/search?limit=100&sort=priority&direction=asc").json()["items"]
    assert [n["priority_score"] for n in all_rows] == sorted(n["priority_score"] for n in all_rows)
    gid = str(tables["nodes"][25]["gid"])
    assert client.get(f"/ranking/search?q={gid}").json()["items"][0]["gid"] == gid
    assert client.get("/ranking/search?q=%25").json()["total"] == 0
    filtered = client.get("/ranking/search?role=peripheral").json()["items"]
    assert filtered and all(n["role"] == "peripheral" for n in filtered)
    cluster = first["items"][0]["cluster_id"]
    filtered = client.get(f"/ranking/search?cluster_id={cluster}").json()["items"]
    assert filtered and all(n["cluster_id"] == cluster for n in filtered)
    assert client.get("/ranking/search?limit=101").status_code == 422
    assert client.get("/ranking/search?sort=bad").status_code == 422


def test_graph_limit_exact_focus_real_edges_and_clusters(client, imported, tables):
    graph = client.get("/graph?limit=3").json()
    assert graph["shown_nodes"] == 3 and graph["truncated"]
    visible = {n["gid"] for n in graph["nodes"]}
    source_pairs = {(str(e["src"]), str(e["dst"])) for e in tables["edges"]}
    assert all(e["src"] in visible and e["dst"] in visible and (e["src"], e["dst"]) in source_pairs for e in graph["edges"])
    gid = str(tables["nodes"][26]["gid"])
    isolated = client.get(f"/graph?gid={gid}&limit=1").json()
    assert [n["gid"] for n in isolated["nodes"]] == [gid]
    assert isolated["edges"] == []
    chain = client.get(f'/graph?gid={tables["nodes"][3]["gid"]}&hops=1').json()
    assert {n["gid"] for n in chain["nodes"]} == {str(tables["nodes"][i]["gid"]) for i in [2, 3, 4]}
    cluster_id = graph["nodes"][0]["cluster_id"]
    cluster = client.get(f"/graph?cluster_id={cluster_id}").json()
    assert all(n["cluster_id"] == cluster_id for n in cluster["nodes"])


def test_csv_contracts_and_deterministic_recalculation(client, imported):
    files = ["nodes_roles.csv", "clusters.csv", "top_nodes.csv"]
    original = {}
    for filename in files:
        response = client.get(f"/exports/{filename}")
        assert response.status_code == 200
        assert filename in response.headers["content-disposition"]
        original[filename] = response.content
    roles = list(csv.DictReader(StringIO(original[files[0]].decode("utf-8-sig"))))
    clusters = list(csv.DictReader(StringIO(original[files[1]].decode("utf-8-sig"))))
    top = list(csv.DictReader(StringIO(original[files[2]].decode("utf-8-sig"))))
    assert len(roles) == len(top) == 27
    assert list(top[0]) == ["rank", "gid", "role", "priority_score", "why"]
    assert list(clusters[0]) == ["cluster_id", "n_nodes", "n_seed", "sum_kzt_internal", "top_gids", "hypothesis"]
    assert sum(int(c["n_nodes"]) for c in clusters) == 27
    assert all(0 < len(r["evidence"]) <= 200 for r in roles)
    assert abs(sum(float(r["pagerank"]) for r in roles) - 1) < 1e-8
    assert client.post("/analysis").status_code == 200
    for filename in files:
        assert client.get(f"/exports/{filename}").content == original[filename]
    assert client.get("/exports/unknown.csv").status_code == 422


@pytest.mark.parametrize("corruption", ["duplicate_gid", "duplicate_edge", "unknown_gid", "amount", "missing_file"])
def test_rejects_inconsistent_import_without_partial_writes(client, tables, corruption):
    if corruption == "duplicate_gid":
        tables["nodes"].append(tables["nodes"][0])
    elif corruption == "duplicate_edge":
        tables["edges"].append(tables["edges"][0])
    elif corruption == "unknown_gid":
        tables["edges"][0]["src"] = 999
    elif corruption == "amount":
        tables["transactions"][0]["sum_kzt"] = 999.0
    else:
        del tables["edges"]
    assert upload(client, tables).status_code == 422
    assert client.get("/dataset").json()["nodes"] == 0


def test_bad_zip_and_repeated_import_preserve_data(client, imported, tables):
    before = client.get("/exports/nodes_roles.csv").content
    assert upload(client, tables).status_code == 409
    assert client.get("/exports/nodes_roles.csv").content == before


def test_corrupted_zip_returns_validation_error(client):
    response = client.post("/dataset/import", files={"file": ("bad.zip", b"not a zip")})
    assert response.status_code == 422


def test_analysis_failure_rolls_back_previous_results(client, imported, monkeypatch):
    from backend.api import analysis
    from backend.services.analytics import run_analysis
    before = client.get("/exports/nodes_roles.csv").content

    def fail_after_flush(session):
        run_analysis(session)
        raise ValidationError("Test calculation failed")

    monkeypatch.setattr(analysis, "run_analysis", fail_after_flush)
    assert client.post("/analysis").status_code == 422
    assert client.get("/exports/nodes_roles.csv").content == before
