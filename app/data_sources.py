from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from .config import settings
from .models import DailySales
from .moysklad import MoySkladClient


class SalesProvider(ABC):
    @abstractmethod
    def load_daily_sales(self, store: str, start: date, end: date) -> dict[date, DailySales]:
        raise NotImplementedError


class MoySkladSalesProvider(SalesProvider):
    def load_daily_sales(self, store: str, start: date, end: date) -> dict[date, DailySales]:
        return MoySkladClient().load_daily_sales(store, start, end)


def get_sales_provider(source: str | None = None) -> SalesProvider:
    source = (source or settings.data_source).strip().lower()
    if source == "moysklad":
        return MoySkladSalesProvider()
    raise ValueError("source must be 'moysklad'")
