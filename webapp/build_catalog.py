"""Export staff prices/stock to the static catalog without customer data.

After /set_price or /set_stock: python webapp/build_catalog.py.
Review and publish catalog.json to update GitHub Pages.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> None:
    from config import config

    out = ROOT / 'webapp' / 'catalog.json'
    catalog = json.loads(out.read_text(encoding='utf-8'))
    with sqlite3.connect(f'file:{config.db_path}?mode=ro', uri=True) as conn:
        for item in catalog:
            row = conn.execute(
                'SELECT p.price, p.in_stock FROM products p '
                'JOIN catalog_links c ON c.product_id = p.id WHERE c.sku = ?',
                (item['sku'],),
            ).fetchone()
            if row:
                item['price'], item['in_stock'] = float(row[0]), bool(row[1])
    out.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Обновлены цены и наличие: {len(catalog)} товаров. Заказы не экспортируются.')


if __name__ == '__main__':
    main()
