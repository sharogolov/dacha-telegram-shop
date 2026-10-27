"""Customer cancellation must never delete history or touch another buyer's order."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import SendMessage

from config import Config
from handlers.customer_orders import cb_cancel_ask, cb_cancel_order, cb_own_order, order_list


async def create_order(db, user_id=100):
    await db.add_to_cart(user_id, 1)
    return await db.create_order(user_id, None, 'Тестовый покупатель', '', '')


def callback(data, user_id=100):
    return SimpleNamespace(data=data, from_user=SimpleNamespace(id=user_id), answer=AsyncMock(),
                           message=SimpleNamespace(answer=AsyncMock()))


@pytest.mark.asyncio
async def test_cancel_own_new_order_and_keep_history(seeded_db):
    order = await create_order(seeded_db)
    call = callback(f'own_cancel:{order.id}')
    config, bot = Config(bot_token='0:test', owner_chat_id=999), AsyncMock()
    with patch('handlers.customer_orders.replace_or_edit', new_callable=AsyncMock) as edit:
        await cb_cancel_order(call, seeded_db, config, bot)
    assert (await seeded_db.get_order(order.id)).status == 'cancelled'
    assert not await seeded_db.list_user_orders(100, active_only=True)
    assert len(await seeded_db.list_user_orders(100)) == 1
    assert 'перенесена в историю' in edit.call_args.args[1]
    assert bot.send_message.call_args.args[0] == 999
    events = await seeded_db.order_status_history(order.id)
    assert events[-1].changed_by == 100
    await cb_cancel_order(call, seeded_db, config, bot)
    assert bot.send_message.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('handler,prefix', [(cb_own_order, 'own_order'), (cb_cancel_ask, 'own_cancel_ask'), (cb_cancel_order, 'own_cancel')])
async def test_cannot_read_or_cancel_another_order(seeded_db, handler, prefix):
    order = await create_order(seeded_db)
    call = callback(f'{prefix}:{order.id}', user_id=101)
    kwargs = {'config': Config(bot_token='0:test'), 'bot': AsyncMock()} if handler == cb_cancel_order else {}
    with patch('handlers.customer_orders.replace_or_edit', new_callable=AsyncMock) as edit:
        await handler(call, seeded_db, **kwargs)
    assert (await seeded_db.get_order(order.id)).status == 'new'
    assert call.answer.call_args.kwargs['show_alert']
    edit.assert_not_awaited()


@pytest.mark.asyncio
async def test_customer_cannot_cancel_order_taken_by_team(seeded_db):
    order = await create_order(seeded_db)
    await seeded_db.update_order_status(order.id, 'confirmed', changed_by=999)
    call, bot = callback(f'own_cancel:{order.id}'), AsyncMock()
    await cb_cancel_order(call, seeded_db, Config(bot_token='0:test', owner_chat_id=999), bot)
    assert (await seeded_db.get_order(order.id)).status == 'confirmed'
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_active_filter_happens_before_pagination(seeded_db):
    first = await create_order(seeded_db)
    for _ in range(12):
        archived = await create_order(seeded_db)
        await seeded_db.update_order_status(archived.id, 'cancelled')
    active = await seeded_db.list_user_orders(100, limit=10, active_only=True)
    assert [order.id for order in active] == [first.id]
    text, keyboard = await order_list(seeded_db, 100)
    callbacks = [b.callback_data for row in keyboard.inline_keyboard for b in row]
    assert f'own_order:{first.id}' in callbacks
    assert len([c for c in callbacks if c.startswith('own_order:')]) == 1
    _, history = await order_list(seeded_db, 100, history=True)
    assert 'own_orders:all:1' in [b.callback_data for row in history.inline_keyboard for b in row]


@pytest.mark.asyncio
async def test_cancellation_survives_notification_failure(seeded_db):
    order = await create_order(seeded_db)
    bot = AsyncMock()
    bot.send_message.side_effect = TelegramForbiddenError(SendMessage(chat_id=999, text='test'), 'blocked')
    with patch('handlers.customer_orders.replace_or_edit', new_callable=AsyncMock):
        await cb_cancel_order(callback(f'own_cancel:{order.id}'), seeded_db,
                              Config(bot_token='0:test', owner_chat_id=999), bot)
    assert (await seeded_db.get_order(order.id)).status == 'cancelled'
