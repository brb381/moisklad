from __future__ import annotations

import time

from fastapi.testclient import TestClient

from app.main import app


def test_job_lifecycle_mock():
    client = TestClient(app)

    create_response = client.post(
        "/reports/gross-turnover",
        json={"store": "Планета", "month": "2026-05", "source": "mock"},
    )
    assert create_response.status_code == 202
    job_id = create_response.json()["job_id"]

    status_payload = None
    for _ in range(40):
        status_response = client.get(f"/reports/jobs/{job_id}")
        assert status_response.status_code == 200
        status_payload = status_response.json()
        if status_payload["status"] == "done":
            break
        time.sleep(0.05)
    assert status_payload is not None
    assert status_payload["status"] == "done"

    download_response = client.get(f"/reports/jobs/{job_id}/download")
    assert download_response.status_code == 200
    assert download_response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert download_response.content.startswith(b"PK")
    assert len(download_response.content) > 8000


def test_stores_endpoint():
    client = TestClient(app)
    response = client.get("/stores")
    assert response.status_code == 200
    payload = response.json()
    assert {
        "code": "planeta",
        "name": "Планета",
        "has_moysklad_id": False,
    } in payload["stores"]


def test_moysklad_stores_diagnostic_endpoint(monkeypatch):
    class FakeMoySkladClient:
        def list_retail_stores(self):
            return [
                {
                    "id": "store-1",
                    "name": "Point 1",
                    "href": "https://api.moysklad.ru/api/remap/1.2/entity/retailstore/store-1",
                    "archived": False,
                    "updated": "2026-06-14 10:00:00.000",
                }
            ]

    monkeypatch.setattr("app.main.MoySkladClient", FakeMoySkladClient)
    client = TestClient(app)

    response = client.get("/moysklad/stores")

    assert response.status_code == 200
    assert response.json()["stores"][0]["id"] == "store-1"


def test_unknown_store_rejected():
    client = TestClient(app)
    response = client.post(
        "/reports/gross-turnover",
        json={"store": "unknown", "month": "2026-05", "source": "mock"},
    )
    assert response.status_code == 404


def test_bad_month_rejected():
    client = TestClient(app)
    response = client.post(
        "/reports/gross-turnover",
        json={"store": "Планета", "month": "202605", "source": "mock"},
    )
    assert response.status_code == 422
