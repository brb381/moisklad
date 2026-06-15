from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

import requests

from .config import settings
from .dates import moysklad_moment_after, moysklad_moment_start
from .models import DailySales
from .stores import StoreConfig, resolve_store


class ReadOnlyMoySkladSession(requests.Session):
    def request(self, method: str, url: str, *args, **kwargs):
        if method.upper() != "GET":
            raise RuntimeError("MoySklad client is read-only: only GET requests are allowed")
        return super().request(method, url, *args, **kwargs)


class MoySkladClient:
    def __init__(self) -> None:
        self.session = ReadOnlyMoySkladSession()
        self.session.headers.update(
            {
                "Accept": "application/json;charset=utf-8",
                "Content-Type": "application/json;charset=utf-8",
            }
        )
        if settings.moysklad_token:
            self.session.headers["Authorization"] = f"Bearer {settings.moysklad_token}"
        elif settings.moysklad_login and settings.moysklad_password:
            self.session.auth = (settings.moysklad_login, settings.moysklad_password)
        else:
            raise RuntimeError(
                "Set MOYSKLAD_TOKEN or MOYSKLAD_LOGIN/MOYSKLAD_PASSWORD in .env"
            )

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{settings.moysklad_base_url}{path}"
        response = self.session.get(url, params=params, timeout=60)
        response.raise_for_status()
        return response.json()

    def _get_all(self, path: str, params: dict[str, Any] | None = None):
        params = dict(params or {})
        params.setdefault("limit", 1000)
        params.setdefault("offset", 0)
        while True:
            payload = self._get(path, params=params)
            rows = payload.get("rows", [])
            yield from rows
            if len(rows) < int(params["limit"]):
                break
            params["offset"] = int(params["offset"]) + int(params["limit"])

    def retail_store_href(self, store: StoreConfig) -> str:
        if store.moysklad_retail_store_id:
            return f"{settings.moysklad_base_url}/entity/retailstore/{store.moysklad_retail_store_id}"

        found = self.find_retail_store_by_name(store.name)
        return found["meta"]["href"]

    def find_retail_store_by_name(self, store: str) -> dict[str, Any]:
        store_lc = store.strip().lower()
        exact = None
        partial = None
        for row in self._get_all("/entity/retailstore", {"search": store}):
            name = (row.get("name") or "").strip()
            if name.lower() == store_lc:
                exact = row
                break
            if store_lc in name.lower() and partial is None:
                partial = row

        found = exact or partial
        if not found:
            raise LookupError(f"Retail store not found in MoySklad: {store}")
        return found

    def list_retail_stores(self) -> list[dict[str, Any]]:
        stores = []
        for row in self._get_all("/entity/retailstore"):
            meta = row.get("meta") or {}
            href = meta.get("href") or ""
            stores.append(
                {
                    "id": href.rstrip("/").split("/")[-1] if href else None,
                    "name": row.get("name"),
                    "href": href,
                    "archived": bool(row.get("archived", False)),
                    "updated": row.get("updated"),
                }
            )
        return stores

    def load_daily_sales(self, store: str, start, end) -> dict:
        store_config = resolve_store(store)
        retail_store_meta = self.retail_store_href(store_config)

        filters = [
            f"moment>={moysklad_moment_start(start)}",
            f"moment<={moysklad_moment_after(end)}",
            f"retailStore={retail_store_meta}",
        ]
        params = {
            "filter": ";".join(filters),
            "expand": "positions",
            "limit": 100,
            "order": "moment,asc",
        }

        result: dict = defaultdict(DailySales)
        for doc in self._get_all("/entity/retaildemand", params):
            moment = doc.get("moment")
            if not moment:
                continue
            day = datetime.strptime(moment[:10], "%Y-%m-%d").date()
            target = result[day]
            target.gross += cents_to_rubles(doc.get("sum", 0))
            target.checks += 1
            target.positions += 1

            positions = doc.get("positions", {}).get("rows") or []
            for position in positions:
                vat_rate = position.get("vat")
                vat_value = cents_to_rubles(position.get("vatSum", 0))
                if vat_rate == 20:
                    target.vat20 += vat_value
                elif vat_rate == 10:
                    target.vat10 += vat_value
                elif vat_rate == 5:
                    target.vat5 += vat_value
                elif vat_rate == 7:
                    target.vat7 += vat_value

        return dict(result)


def cents_to_rubles(value: Any) -> float:
    return round(float(value or 0) / 100.0, 2)
