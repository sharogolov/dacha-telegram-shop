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
        from_user=SimpleNamespace(id=user_id, username=None, full_name="Имя из Telegram"),
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
    assert any('Заявка #1 сохранена' in call.args[0] for call in msg.answer.call_args_list)


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


@pytest.mark.asyncio
async def test_quick_order_uses_verified_telegram_profile(seeded_db):
    raw = payload(version=3)
    data = json.loads(raw)
    del data['customer']
    # A forged client profile must not control the buyer identity.
    data['user_id'] = 123456
    msg = message(json.dumps(data))
    await on_webapp_data(msg, AsyncMock(), seeded_db, AsyncMock(), Config(bot_token='0:test', owner_chat_id=999))
    order = (await seeded_db.list_orders())[0]
    assert order.user_id == 100
    assert order.full_name == 'Имя из Telegram'
    assert order.username is None
    assert order.phone == '' and order.address == ''
    from handlers.order_admin import _order_card, _status_kb
    assert 'tg://user?id=100' in _order_card(order)
    buttons = [b for row in _status_kb(order).inline_keyboard for b in row]
    assert any(b.callback_data == f'order_chat:{order.id}' for b in buttons)


@pytest.mark.asyncio
async def test_legacy_profile_name_is_not_trusted(seeded_db):
    msg = message(payload(customer={'full_name': 'Поддельное имя', 'phone': '', 'address': ''}))
    await on_webapp_data(msg, AsyncMock(), seeded_db, AsyncMock(), Config(bot_token='0:test'))
    assert (await seeded_db.list_orders())[0].full_name == 'Имя из Telegram'


@pytest.mark.asyncio
async def test_order_chat_without_username_both_ways_and_authorization(seeded_db):
    from handlers.order_chat import send_order_chat, start_order_chat
    await on_webapp_data(message(), AsyncMock(), seeded_db, AsyncMock(), Config(bot_token='0:test'))
    order = (await seeded_db.list_orders())[0]
    config = Config(bot_token='0:test', owner_chat_id=999, admin_ids=[888])
    call = SimpleNamespace(from_user=SimpleNamespace(id=777), answer=AsyncMock(),
                           message=message(user_id=777), data=f'order_chat:{order.id}')
    state = AsyncMock()
    await start_order_chat(call, state, seeded_db, config)
    assert call.answer.call_args.kwargs['show_alert']
    state.set_state.assert_not_awaited()
    call.from_user.id = 888
    await start_order_chat(call, state, seeded_db, config)
    state.set_state.assert_awaited_once()
    state.get_data.return_value = {'order_chat_id': order.id}
    bot = AsyncMock()
    outgoing = message(user_id=888)
    outgoing.text = 'Уточните удобный способ получения <test>'
    await send_order_chat(outgoing, state, seeded_db, config, bot)
    assert bot.send_message.call_args.args[0] == 100
    assert '&lt;test&gt;' in bot.send_message.call_args.args[1]
    incoming = message(user_id=100)
    incoming.text = 'Хочу забрать самовывозом'
    await send_order_chat(incoming, state, seeded_db, config, bot)
    assert bot.send_message.call_args.args[0] == 999
    forbidden = message(user_id=777)
    forbidden.text = 'Посторонний'
    before = bot.send_message.await_count
    await send_order_chat(forbidden, state, seeded_db, config, bot)
    assert bot.send_message.await_count == before
