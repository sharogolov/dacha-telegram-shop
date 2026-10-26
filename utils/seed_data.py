"""Стартовый каталог вин магазина «Дача Сердюка»."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from database import Database

CATEGORIES = {"Оранжевое вино": "🟠", "Красное вино": "🍷", "Розе": "🌸"}
PRODUCTS = [
    {"category": "Оранжевое вино", "name": "Оранж летний", "description": "Лёгкое и свежее вино из Сибирькового: мёд, гречиха, яблочная кислинка и сухой финиш.", "price": 1400.0, "photo_url": "photos/wines/pdf-05.png"},
    {"category": "Оранжевое вино", "name": "Сибирьковый", "description": "Выдержанное в стали, с зелёным яблоком, цитрусом и хрустящей структурой. Лёгкий летний аперитив.", "price": 1800.0, "photo_url": "photos/wines/pdf-06.png"},
    {"category": "Оранжевое вино", "name": "Оранж Ркацители", "description": "Белый грузинский сорт: печёное яблоко, свежее мелло и мандариновая цедра. Сложное, с тонкими танинами.", "price": 1600.0, "photo_url": "photos/wines/pdf-07.png"},
    {"category": "Оранжевое вино", "name": "Ркацители", "description": "Выдержка в старой дубовой бочке: вяленая хурма, мёд, смола и сушёная мандариновая корка.", "price": 2000.0, "photo_url": "photos/wines/pdf-08.png"},
    {"category": "Красное вино", "name": "Красностоп Золотовский", "description": "Сдержанное и свежее, с чёрным перцем, черносливом и травяной горчинкой. Выдержано в стали.", "price": 1900.0, "photo_url": "photos/wines/pdf-10.png"},
    {"category": "Красное вино", "name": "Казачье", "description": "Красностоп Золотовский из дубовой бочки: чёрная смородина, черёмуха, пряности и долгое послевкусие.", "price": 2300.0, "photo_url": "photos/wines/pdf-11.png"},
    {"category": "Красное вино", "name": "Саперави", "description": "Мощное и интенсивное грузинское вино с вишней, горчинкой, танинами и хорошим потенциалом выдержки.", "price": 1600.0, "photo_url": "photos/wines/pdf-12.png"},
    {"category": "Красное вино", "name": "Саперави выдержанный", "description": "Бочковая версия с дымным сырокопчёным ароматом, горьким шоколадом и плотной структурой.", "price": 2000.0, "photo_url": "photos/wines/pdf-13.png"},
    {"category": "Красное вино", "name": "Станичное", "description": "Купаж Каберне Совиньона и Саперави: дуб, сушёная клюква, чёрный перец и глубокое послевкусие.", "price": 2000.0, "photo_url": "photos/wines/pdf-14.png"},
    {"category": "Красное вино", "name": "Поречное", "description": "Купаж Каберне Совиньона, Саперави и Красностопа Золотовского. Плотное, гармоничное, с ягодными нотами.", "price": 2300.0, "photo_url": "photos/wines/pdf-15.png"},
    {"category": "Розе", "name": "Каберне Совиньон Розе", "description": "Пронзительное и сдержанное розе с малиной, карамелью и брусничным тартом. Пить слегка охлаждённым.", "price": 1800.0, "photo_url": "photos/wines/pdf-16.png"},
    {"category": "Розе", "name": "Каберне Совиньон Глу Глу", "description": "Яркое и звонкое розе с вишнёвым леденцом, клубничным желе и пикантной брусничной горчинкой.", "price": 1800.0, "photo_url": "photos/wines/pdf-17.png"},
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
