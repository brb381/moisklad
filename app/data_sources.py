from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from .config import settings
from .models import DailySales
from .moysklad import MoySkladClient


class SalesProvider(ABC):
    @abstractmethod
    async def load_daily_sales(self, store: str, start: date, end: date) -> dict[date, DailySales]:
        raise NotImplementedError


class MoySkladSalesProvider(SalesProvider):
    async def load_daily_sales(self, store: str, start: date, end: date) -> dict[date, DailySales]:
        async with MoySkladClient() as client:
            return await client.load_daily_sales(store, start, end)


def get_sales_provider(source: str | None = None) -> SalesProvider:
    source = (source or settings.data_source).strip().lower()
    if source == "moysklad":
        return MoySkladSalesProvider()
    raise ValueError("source must be 'moysklad'")
