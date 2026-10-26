"""Стартовый каталог вин магазина «Дача Сердюка»."""
from __future__ import annotations

from database import Database

CATEGORIES = {"Красное вино": "🍷", "Белое вино": "🥂", "Розовое вино": "🌸", "Игристое": "✨"}
PRODUCTS = [
    {"category": "Красное вино", "name": "Красное сухое «Дача»", "description": "Насыщенное сухое вино для ужина и дружеских встреч.", "price": 1290.0, "photo_url": ""},
    {"category": "Красное вино", "name": "Красное полусладкое «Сердюк»", "description": "Мягкое ягодное вино с приятным послевкусием.", "price": 1190.0, "photo_url": ""},
    {"category": "Белое вино", "name": "Белое сухое «Лето»", "description": "Легкое освежающее вино к рыбе и овощам.", "price": 1090.0, "photo_url": ""},
    {"category": "Розовое вино", "name": "Розовое полусухое «Сад»", "description": "Ароматное розовое вино для теплого вечера.", "price": 1250.0, "photo_url": ""},
    {"category": "Игристое", "name": "Игристое «Праздник»", "description": "Праздничное игристое для особого случая.", "price": 1490.0, "photo_url": ""},
]

async def seed_if_empty(db: Database) -> int:
    actual_count = await db.count_products()
    if actual_count == len(PRODUCTS):
        first = await db.get_product(1, include_out_of_stock=True)
        if first and first.name == PRODUCTS[0]["name"]:
            return 0
    if actual_count:
        await db.conn.execute("DELETE FROM products")
        await db.conn.execute("DELETE FROM categories")
        await db.conn.execute("DELETE FROM sqlite_sequence WHERE name IN ('products', 'categories')")
        await db.conn.commit()
    category_ids = {name: await db.add_category(name, emoji) for name, emoji in CATEGORIES.items()}
    for product in PRODUCTS:
        await db.add_product(category_id=category_ids[product["category"]], name=product["name"], description=product["description"], price=product["price"], photo_url=product["photo_url"])
    return len(PRODUCTS)
