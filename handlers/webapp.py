"""Receive a complete checkout from a keyboard Mini App; trust only DB prices."""
from __future__ import annotations

import json
import re
from html import escape

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from config import Config
from database import CartItem, Database
from handlers.order_admin import notify_manager
from handlers.order_chat import reply_keyboard

router = Router(name='webapp')
PHONE_RE = re.compile(r'^[+\d][\d\s\-()]{6,19}$')


def parse_checkout(raw: str) -> dict:
    if len(raw.encode('utf-8')) > 4096:
        raise ValueError('Заявка слишком большая. Сократите комментарий.')
    payload = json.loads(raw)
    if not isinstance(payload, dict) or payload.get('version') not in (2, 3):
        raise ValueError('Обновите магазин: /start → «Открыть магазин».')
    request_id = payload.get('request_id')
    if not isinstance(request_id, str) or not re.fullmatch(r'[a-zA-Z0-9-]{16,64}', request_id):
        raise ValueError('Не удалось прочитать номер отправки. Откройте магазин заново.')
    customer = payload.get('customer', {})
    if not isinstance(customer, dict):
        raise ValueError('Не удалось прочитать данные заявки.')
    # Optional fields from older Mini App versions. Account identity is always
    # taken from Telegram's update, never from client-supplied user data.
    details = {}
    for key, high in [('phone', 20), ('address', 250)]:
        value = customer.get(key, '')
        if not isinstance(value, str) or len(value.strip()) > high:
            raise ValueError('Проверьте дополнительные данные заявки.')
        details[key] = value.strip()
    if details['phone'] and not PHONE_RE.fullmatch(details['phone']):
        raise ValueError('Проверьте номер телефона.')
    payload['customer'] = details
    items = payload.get('items')
    if not isinstance(items, list) or not 1 <= len(items) <= 30:
        raise ValueError('В заявке должно быть от 1 до 30 позиций.')
    seen = set()
    for item in items:
        if not isinstance(item, dict):
            raise ValueError('Некорректная позиция заявки.')
        sku, qty = item.get('sku'), item.get('quantity')
        if not isinstance(sku, str) or not re.fullmatch(r'dacha-\d{2}', sku) or sku in seen:
            raise ValueError('Проверьте товары в корзине.')
        if type(qty) is not int or not 1 <= qty <= 99:
            raise ValueError('Допустимо от 1 до 99 штук каждого товара.')
        if type(item.get('price')) not in (int, float) or not 0 <= item['price'] <= 1_000_000:
            raise ValueError('Не удалось прочитать цену. Обновите каталог.')
        seen.add(sku)
    return payload


@router.message(F.web_app_data, F.chat.type == 'private')
async def on_webapp_data(message: Message, state: FSMContext, db: Database,
                         bot: Bot, config: Config) -> None:
    # Mini App can explicitly clear the bot-side cart before closing itself.
    try:
        raw_payload = json.loads(message.web_app_data.data)
    except (TypeError, ValueError, json.JSONDecodeError):
        raw_payload = None
    if isinstance(raw_payload, dict) and raw_payload.get('action') == 'clear_cart':
        await db.clear_cart(message.from_user.id)
        await state.clear()
        await message.answer('🧺 Корзина очищена.')
        return
    try:
        payload = parse_checkout(message.web_app_data.data)
        async with db.order_lock:
            order = await db.get_submission(message.from_user.id, payload['request_id'])
            duplicate = order is not None
            if not order:
                items = []
                for item in payload['items']:
                    product = await db.get_catalog_product(item['sku'])
                    if not product:
                        raise ValueError('Один из товаров закончился. Откройте корзину и обновите выбор.')
                    if round(product.price * 100) != round(item['price'] * 100):
                        raise ValueError(f'Цена «{product.name}» изменилась. Заявка не создана; уточните цену у менеджера и обновите каталог.')
                    items.append(CartItem(product_id=product.id, name=product.name,
                                          price=product.price, quantity=item['quantity']))
                try:
                    order = await db.create_order(
                        message.from_user.id, message.from_user.username,
                        full_name=message.from_user.full_name,
                        **payload['customer'], items=items, request_id=payload['request_id'],
                    )
                except Exception:
                    await db.conn.rollback()
                    raise
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        await message.answer('Не удалось принять заявку. ' + escape(str(exc)))
        return
    await state.clear()
    lines = [f'✅ <b>Заявка #{order.id} сохранена</b>', '', 'Статус: новая заявка.']
    lines.extend(f'• {escape(i.name)} × {i.quantity}' for i in order.items)
    unknown = any(not i.price for i in order.items)
    lines.append(f"\n{'Сумма известных цен' if unknown else 'Итого'}: <b>{order.total:.0f} ₽</b>")
    if unknown:
        lines.append('Цены отдельных позиций уточнит менеджер.')
    lines.append('Для связи используем ваш Telegram. Детали получения уточнит менеджер в переписке.')
    await message.answer('\n'.join(lines), reply_markup=reply_keyboard(order.id))
    if not duplicate and not await notify_manager(bot, config, order):
        await message.answer('Заявка сохранена, но уведомление менеджеру пока не доставлено. Команда увидит её в общем списке.')
