from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime
from typing import Any

import httpx

from .config import settings
from .dates import moysklad_moment_after, moysklad_moment_start
from .models import DailySales
from .stores import StoreConfig, resolve_store


_request_semaphore = asyncio.Semaphore(settings.moysklad_max_concurrent_requests)
_rate_lock = asyncio.Lock()
_last_request_at = 0.0


class MoySkladApiError(RuntimeError):
    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        super().__init__(f"MoySklad API error {status_code}: {message}")


class ReadOnlyAsyncClient(httpx.AsyncClient):
    async def request(self, method: str, url: httpx.URL | str, *args, **kwargs) -> httpx.Response:
        if method.upper() != "GET":
            raise RuntimeError("MoySklad client is read-only: only GET requests are allowed")
        return await super().request(method, url, *args, **kwargs)


class MoySkladClient:
    def __init__(self) -> None:
        headers = {
            "Accept": "application/json;charset=utf-8",
            "Content-Type": "application/json;charset=utf-8",
        }
        auth = None
        if settings.moysklad_token:
            headers["Authorization"] = f"Bearer {settings.moysklad_token}"
        elif settings.moysklad_login and settings.moysklad_password:
            auth = (settings.moysklad_login, settings.moysklad_password)
        else:
            raise RuntimeError(
                "Set MOYSKLAD_TOKEN or MOYSKLAD_LOGIN/MOYSKLAD_PASSWORD in .env"
            )

        self.client = ReadOnlyAsyncClient(
            base_url=settings.moysklad_base_url,
            headers=headers,
            auth=auth,
            timeout=60,
        )

    async def __aenter__(self) -> "MoySkladClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.client.aclose()

    async def _respect_rate_limit(self) -> None:
        global _last_request_at
        async with _rate_lock:
            now = asyncio.get_running_loop().time()
            wait_for = settings.moysklad_min_request_interval_seconds - (now - _last_request_at)
            if wait_for > 0:
                await asyncio.sleep(wait_for)
            _last_request_at = asyncio.get_running_loop().time()

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        async with _request_semaphore:
            await self._respect_rate_limit()
            response = await self.client.get(path, params=params)

        if response.status_code in {429, 500, 502, 503, 504}:
            response = await self._retry_get(path, params)

        if response.status_code >= 400:
            raise MoySkladApiError(response.status_code, safe_error_body(response))
        return response.json()

    async def _retry_get(
        self, path: str, params: dict[str, Any] | None = None
    ) -> httpx.Response:
        delay = settings.moysklad_retry_base_delay_seconds
        last_response: httpx.Response | None = None
        for _ in range(settings.moysklad_retry_attempts):
            await asyncio.sleep(delay)
            async with _request_semaphore:
                await self._respect_rate_limit()
                last_response = await self.client.get(path, params=params)
            if last_response.status_code not in {429, 500, 502, 503, 504}:
                return last_response
            delay *= 2
        assert last_response is not None
        return last_response

    async def _get_all(self, path: str, params: dict[str, Any] | None = None):
        params = dict(params or {})
        params.setdefault("limit", 1000)
        params.setdefault("offset", 0)
        while True:
            payload = await self._get(path, params=params)
            rows = payload.get("rows", [])
            for row in rows:
                yield row
            if len(rows) < int(params["limit"]):
                break
            params["offset"] = int(params["offset"]) + int(params["limit"])

    async def retail_store_href(self, store: StoreConfig) -> str:
        if store.moysklad_retail_store_id:
            return f"{settings.moysklad_base_url}/entity/retailstore/{store.moysklad_retail_store_id}"

        found = await self.find_retail_store_by_name(store.name)
        return found["meta"]["href"]

    async def find_retail_store_by_name(self, store: str) -> dict[str, Any]:
        store_lc = store.strip().lower()
        exact = None
        partial = None
        async for row in self._get_all("/entity/retailstore", {"search": store}):
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

    async def list_retail_stores(self) -> list[dict[str, Any]]:
        stores = []
        async for row in self._get_all("/entity/retailstore"):
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

    async def load_daily_sales(self, store: str, start, end) -> dict:
        store_config = resolve_store(store)
        retail_store_meta = await self.retail_store_href(store_config)

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
        async for doc in self._get_all("/entity/retaildemand", params):
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


def safe_error_body(response: httpx.Response) -> str:
    text = response.text[:1000]
    return text.replace(settings.moysklad_token or "", "[token]") if text else response.reason_phrase


def cents_to_rubles(value: Any) -> float:
    return round(float(value or 0) / 100.0, 2)
