from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .config import ROOT_DIR


@dataclass(frozen=True)
class StoreConfig:
    code: str
    name: str
    aliases: tuple[str, ...]
    template_hint: str
    moysklad_retail_store_id: str | None = None


def load_stores() -> tuple[StoreConfig, ...]:
    path = ROOT_DIR / "stores.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    stores = []
    for row in payload:
        stores.append(
            StoreConfig(
                code=row["code"],
                name=row["name"],
                aliases=tuple(row.get("aliases") or ()),
                template_hint=row.get("template_hint") or row["name"],
                moysklad_retail_store_id=row.get("moysklad_retail_store_id"),
            )
        )
    return tuple(stores)


STORES: tuple[StoreConfig, ...] = load_stores()


def normalize_store_name(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def resolve_store(value: str) -> StoreConfig:
    normalized = normalize_store_name(value)
    if not normalized:
        raise ValueError("store is required")

    for store in STORES:
        names = {normalize_store_name(store.code), normalize_store_name(store.name)}
        names.update(normalize_store_name(alias) for alias in store.aliases)
        if normalized in names:
            return store
    raise LookupError(f"Unknown store: {value}")


def list_stores() -> list[dict[str, str]]:
    return [
        {
            "code": store.code,
            "name": store.name,
            "has_moysklad_id": bool(store.moysklad_retail_store_id),
        }
        for store in STORES
    ]


def find_template_for_store(store: StoreConfig) -> Path:
    templates = sorted(
        path for path in ROOT_DIR.glob("*.xlsx") if "валовом_обороте" in path.stem.lower()
    )
    if not templates:
        raise FileNotFoundError("No report template xlsx files found")

    hint = normalize_store_name(store.template_hint)
    for path in templates:
        if hint in normalize_store_name(path.stem):
            return path
    raise FileNotFoundError(f"No report template found for store: {store.name}")
