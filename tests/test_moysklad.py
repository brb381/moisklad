from __future__ import annotations

from app.models import DailySales
from app.moysklad import MoySkladClient
from app.stores import StoreConfig


def test_retail_store_href_uses_configured_id_without_search(monkeypatch):
    client = MoySkladClient.__new__(MoySkladClient)

    def fail_search(_store_name):
        raise AssertionError("name search must not be called when ID is configured")

    client.find_retail_store_by_name = fail_search
    store = StoreConfig(
        code="x",
        name="X",
        aliases=(),
        template_hint="X",
        moysklad_retail_store_id="12345678-1234-1234-1234-123456789abc",
    )

    href = client.retail_store_href(store)
    assert href.endswith("/entity/retailstore/12345678-1234-1234-1234-123456789abc")


def test_list_retail_stores_extracts_ids():
    client = MoySkladClient.__new__(MoySkladClient)
    client._get_all = lambda _path: iter(
        [
            {
                "name": "Point 1",
                "archived": False,
                "updated": "2026-06-14 10:00:00.000",
                "meta": {
                    "href": "https://api.moysklad.ru/api/remap/1.2/entity/retailstore/store-1"
                },
            }
        ]
    )

    stores = client.list_retail_stores()

    assert stores == [
        {
            "id": "store-1",
            "name": "Point 1",
            "href": "https://api.moysklad.ru/api/remap/1.2/entity/retailstore/store-1",
            "archived": False,
            "updated": "2026-06-14 10:00:00.000",
        }
    ]


def test_cents_to_daily_sales_net():
    sales = DailySales(gross=1200, vat20=200)
    assert sales.net == 1000
