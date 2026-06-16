from __future__ import annotations

import asyncio

from app.moysklad import MoySkladClient


async def main() -> None:
    async with MoySkladClient() as client:
        stores = await client.list_retail_stores()

    print("stores_count=", len(stores))
    for store in stores:
        print(
            f"{store.get('id') or ''} | {store.get('name') or ''} | "
            f"archived={store.get('archived')}"
        )


if __name__ == "__main__":
    asyncio.run(main())
