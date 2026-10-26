"""Import the published catalog without deleting staff changes or old orders."""
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from database import Database

CATALOG_PATH = Path(__file__).resolve().parent.parent / 'webapp' / 'catalog.json'
PRODUCTS = json.loads(CATALOG_PATH.read_text(encoding='utf-8'))
CATEGORIES = {p['category']: '' for p in PRODUCTS}
LEGACY_NAMES = {
    'Ркацители в дубе': 'Ркацители',
    'Саперави в дубе': 'Саперави выдержанный',
    'Станичное в дубе': 'Станичное',
    'Поречное в дубе': 'Поречное',
    'Каберне Совиньон «Глу-Глу»': 'Каберне Совиньон Глу Глу',
}


async def seed_if_empty(db: Database) -> int:
    inserted = 0
    existing = {p.name: p for p in await db.list_all_products()}
    for item in PRODUCTS:
        if await db.get_catalog_product(item['sku'], include_out_of_stock=True):
            continue
        product = existing.get(item['name']) or existing.get(LEGACY_NAMES.get(item['name']))
        if product:
            product_id = product.id
        else:
            category_id = await db.add_category(item['category'])
            product_id = await db.add_product(
                category_id, item['name'],
                f"Безалкогольное, {item['abv']}%. " + item['taste'],
                float(item['price']), 'webapp/' + item['image'],
            )
            if not item.get('in_stock', True):
                await db.update_product_availability(product_id, False)
            inserted += 1
        await db.conn.execute(
            'INSERT INTO catalog_links (sku, product_id) VALUES (?, ?)',
            (item['sku'], product_id),
        )
        await db.conn.commit()
    return inserted
