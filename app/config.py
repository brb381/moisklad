from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")


def optional_env(name: str) -> str | None:
    value = (os.getenv(name) or "").strip()
    if not value or value.startswith("your_"):
        return None
    return value


@dataclass(frozen=True)
class Settings:
    moysklad_base_url: str = os.getenv(
        "MOYSKLAD_BASE_URL", "https://api.moysklad.ru/api/remap/1.2"
    ).rstrip("/")
    moysklad_token: str | None = optional_env("MOYSKLAD_TOKEN")
    moysklad_login: str | None = optional_env("MOYSKLAD_LOGIN")
    moysklad_password: str | None = optional_env("MOYSKLAD_PASSWORD")

    report_tenant: str = os.getenv("REPORT_TENANT", "ИП Леонтьев Д.С,")
    report_trade_name: str = os.getenv("REPORT_TRADE_NAME", "5LB")
    report_rent_contract: str = os.getenv("REPORT_RENT_CONTRACT", "№1276К-25-ДАК")
    report_room: str = os.getenv("REPORT_ROOM", "A1-2")
    report_tax_system: str = os.getenv(
        "REPORT_TAX_SYSTEM", "ОСНО  ;         УСНО ;     Патент"
    )
    report_fiscal_operator: str = os.getenv("REPORT_FISCAL_OPERATOR", "Эватор")
    data_source: str = os.getenv("DATA_SOURCE", "mock")
    max_report_workers: int = int(os.getenv("MAX_REPORT_WORKERS", "2"))


settings = Settings()
