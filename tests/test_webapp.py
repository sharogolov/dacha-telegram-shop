"""Checkout integration without contacting Telegram or using the local shop DB."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import SendMessage

from config import Config
from handlers.admin import cmd_orders_all
from handlers.order_admin import cb_team_orders
from handlers.start import show_shop_menu
from handlers.webapp import on_webapp_data, parse_checkout
from utils.seed_data import seed_if_empty


def payload(**changes):
    data = {
        'version': 2, 'request_id': 'test-request-0000001',
        'customer': {'full_name': 'Тестовый покупатель', 'phone': '+10000000000', 'address': 'Учебный адрес'},
        'items': [{'sku': 'dacha-01', 'quantity': 2, 'price': 1400}],
    }
    data.update(changes)
    return json.dumps(data)


def message(raw=None, user_id=100):
    return SimpleNamespace(
        from_user=SimpleNamespace(id=user_id, username=None),
        chat=SimpleNamespace(type='private'),
        web_app_data=SimpleNamespace(data=raw or payload()),
        answer=AsyncMock(),
    )


@pytest.mark.parametrize('raw', ['null', '[]', '{}', payload(items=[None]),
    payload(items=[{'sku': 'dacha-01', 'quantity': True, 'price': 1400}]),
    payload(items=[{'sku': 'dacha-01', 'quantity': 100, 'price': 1400}]),
    payload(items=[{'sku': 'dacha-01', 'quantity': 1, 'price': float('nan')}]),
])
def test_reject_malformed_checkout(raw):
    with pytest.raises(ValueError):
        parse_checkout(raw)


@pytest.mark.asyncio
async def test_checkout_snapshot_manager_and_duplicate(seeded_db):
    db = seeded_db
    msg, state, bot = message(), AsyncMock(), AsyncMock()
    config = Config(bot_token='0:test', owner_chat_id=999, admin_ids=[888])
    # Existing bot cart must survive Mini App checkout.
    await db.add_to_cart(100, 2)
    await asyncio.gather(*(on_webapp_data(msg, state, db, bot, config) for _ in range(2)))
    orders = await db.list_orders()
    assert len(orders) == 1
    assert orders[0].total == 2800
    assert orders[0].items[0].quantity == 2
    assert orders[0].status == 'new'
    assert len(await db.get_cart(100)) == 1
    assert bot.send_message.await_count == 1
    assert bot.send_message.call_args.args[0] == 999
    assert config.team_ids == {888, 999}
    assert 'Заявка #1 сохранена' in msg.answer.call_args.args[0]


@pytest.mark.asyncio
async def test_reject_changed_stock_and_price(seeded_db):
    db = seeded_db
    product = await db.get_catalog_product('dacha-01')
    await db.update_product_availability(product.id, False)
    msg, state, bot = message(), AsyncMock(), AsyncMock()
    config = Config(bot_token='0:test', owner_chat_id=999)
    await on_webapp_data(msg, state, db, bot, config)
    assert not await db.list_orders()
    assert 'закончился' in msg.answer.call_args.args[0]
    await db.update_product_availability(product.id, True)
    await db.update_product_price(product.id, 1777)
    await on_webapp_data(msg, state, db, bot, config)
    assert not await db.list_orders()
    assert 'изменилась' in msg.answer.call_args.args[0]
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_import_preserves_staff_changes_and_legacy_ids(db):
    category_id = await db.add_category('Старый каталог')
    pid = await db.add_product(category_id, 'Ркацители', 'Сохранить описание', 1777)
    await db.update_product_availability(pid, False)
    await seed_if_empty(db)
    product = await db.get_catalog_product('dacha-04', include_out_of_stock=True)
    assert product.id == pid
    assert product.price == 1777 and not product.in_stock
    assert product.description == 'Сохранить описание'
    assert await seed_if_empty(db) == 0


@pytest.mark.asyncio
async def test_manager_failure_keeps_order_and_staff_can_view(seeded_db):
    bot, state, msg = AsyncMock(), AsyncMock(), message()
    bot.send_message.side_effect = TelegramForbiddenError(SendMessage(chat_id=999, text='test'), 'blocked')
    config = Config(bot_token='0:test', owner_chat_id=999, admin_ids=[888])
    await on_webapp_data(msg, state, seeded_db, bot, config)
    assert len(await seeded_db.list_orders()) == 1
    assert 'не доставлено' in msg.answer.call_args.args[0]
    staff_message = message(user_id=888)
    await cmd_orders_all(staff_message, seeded_db, config)
    assert 'Заказы команды' in staff_message.answer.call_args.args[0]
    outsider = message(user_id=777)
    await cmd_orders_all(outsider, seeded_db, config)
    outsider.answer.assert_not_awaited()
    call = SimpleNamespace(from_user=SimpleNamespace(id=777), answer=AsyncMock(), message=outsider)
    await cb_team_orders(call, seeded_db, config)
    assert call.answer.call_args.kwargs['show_alert']


@pytest.mark.asyncio
async def test_shop_uses_keyboard_webapp_for_send_data():
    msg = message()
    config = Config(bot_token='0:test', webapp_url='https://example.com', admin_ids=[100])
    await show_shop_menu(msg, config, 100)
    keyboard = msg.answer.call_args.kwargs['reply_markup'].keyboard
    assert keyboard[0][0].web_app.url == 'https://example.com'
    assert any(button.text == '📋 Заказы команды' for row in keyboard for button in row)
