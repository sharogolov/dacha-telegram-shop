"""Regression checks for bot cart cleanup, stale buttons and per-user reset."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from config import Config
from handlers.cart import cb_clear, cb_qty
from handlers.checkout import start_checkout
from handlers.start import restart_shop
from handlers.webapp import on_webapp_data
from tests.test_webapp import message, payload


def callback(data, user_id=100):
    return SimpleNamespace(data=data, from_user=SimpleNamespace(id=user_id),
                           message=message(user_id=user_id), answer=AsyncMock())


@pytest.mark.asyncio
async def test_clear_old_bot_cart_replaces_stale_message(seeded_db):
    await seeded_db.add_to_cart(100, 1)
    await seeded_db.add_to_cart(101, 2)
    call = callback('clear_cart')
    with patch('handlers.cart.replace_or_edit', new_callable=AsyncMock) as edit:
        await cb_clear(call, seeded_db)
    assert await seeded_db.get_cart(100) == []
    assert len(await seeded_db.get_cart(101)) == 1
    assert 'Корзина пуста' in edit.call_args.args[1]
    callbacks = [b.callback_data for row in edit.call_args.args[2].inline_keyboard for b in row]
    assert 'checkout' not in callbacks


@pytest.mark.asyncio
async def test_old_checkout_button_replaces_empty_cart(seeded_db):
    call, state = callback('checkout'), AsyncMock()
    with patch('handlers.cart.replace_or_edit', new_callable=AsyncMock) as edit:
        await start_checkout(call, seeded_db, state)
    assert 'Корзина пуста' in edit.call_args.args[1]
    state.clear.assert_awaited_once()
    state.set_state.assert_not_awaited()


@pytest.mark.asyncio
async def test_remove_last_item_from_old_cart(seeded_db):
    await seeded_db.add_to_cart(100, 1)
    call = callback('qty:1:rm')
    with patch('handlers.cart.replace_or_edit', new_callable=AsyncMock) as edit:
        await cb_qty(call, seeded_db)
    assert not await seeded_db.get_cart(100)
    assert 'Корзина пуста' in edit.call_args.args[1]


@pytest.mark.asyncio
async def test_restart_only_resets_current_cart_not_order_history(seeded_db):
    msg, state = message(), AsyncMock()
    await on_webapp_data(msg, state, seeded_db, AsyncMock(), Config(bot_token='0:test'))
    await seeded_db.add_to_cart(100, 1)
    await seeded_db.add_to_cart(101, 2)
    await restart_shop(msg, state, seeded_db, Config(bot_token='0:test', webapp_url='https://example.com'))
    assert not await seeded_db.get_cart(100)
    assert len(await seeded_db.get_cart(101)) == 1
    assert len(await seeded_db.list_user_orders(100)) == 1


@pytest.mark.asyncio
async def test_failed_submission_keeps_cart(seeded_db):
    await seeded_db.add_to_cart(100, 2)
    msg = message(payload(items=[{'sku': 'dacha-01', 'quantity': 1, 'price': 1}]))
    await on_webapp_data(msg, AsyncMock(), seeded_db, AsyncMock(), Config(bot_token='0:test'))
    assert len(await seeded_db.get_cart(100)) == 1
    assert not await seeded_db.list_orders()


@pytest.mark.asyncio
async def test_webapp_clear_does_not_create_order(seeded_db):
    await seeded_db.add_to_cart(100, 1)
    await seeded_db.add_to_cart(101, 2)
    msg = message('{"version":3,"action":"clear_cart"}')
    await on_webapp_data(msg, AsyncMock(), seeded_db, AsyncMock(), Config(bot_token='0:test'))
    assert not await seeded_db.get_cart(100)
    assert len(await seeded_db.get_cart(101)) == 1
    assert not await seeded_db.list_orders()
