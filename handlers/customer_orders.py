"""Customer order history and cancellation of their own unconfirmed requests."""
import logging
from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import Config
from database import STATUS_LABELS, Database, OrderSummary
from utils.parsing import safe_int
from utils.telegram import replace_or_edit

router = Router(name='customer_orders')
router.message.filter(F.chat.type == 'private')
router.callback_query.filter(F.message.chat.type == 'private')
log = logging.getLogger(__name__)


def navigation():
    builder = InlineKeyboardBuilder()
    builder.button(text='📦 Активные заявки', callback_data='my_orders')
    builder.button(text='🗂 История', callback_data='own_orders:all:0')
    builder.adjust(1)
    return builder.as_markup()


async def order_list(db: Database, user_id: int, *, history: bool = False, page: int = 0):
    page = max(0, min(page, 100000))
    orders = await db.list_user_orders(user_id, limit=11, offset=page * 10, active_only=not history)
    builder = InlineKeyboardBuilder()
    for order in orders[:10]:
        builder.button(text=f'#{order.id} · {order.total:.0f} ₽ · {STATUS_LABELS.get(order.status, order.status)}',
                       callback_data=f'own_order:{order.id}')
    scope = 'all' if history else 'active'
    if page:
        builder.button(text='← Новее', callback_data=f'own_orders:{scope}:{page - 1}')
    if len(orders) > 10:
        builder.button(text='Старее →', callback_data=f'own_orders:{scope}:{page + 1}')
    builder.button(text='📦 Активные заявки' if history else '🗂 История',
                   callback_data='my_orders' if history else 'own_orders:all:0')
    builder.button(text='Обновить', callback_data=f'own_orders:{scope}:{page}')
    builder.adjust(1)
    title = 'История заявок' if history else 'Активные заявки'
    text = f'📦 <b>{title}</b>'
    if not orders:
        text += '\n\nЗаявок пока нет.' if history else '\n\nАктивных заявок нет. Завершённые и отменённые доступны в истории.'
    else:
        text += '\n\nВыберите заявку для просмотра.'
    return text, builder.as_markup()


@router.message(Command('orders'))
@router.message(F.text == '📦 Мои заявки')
async def cmd_my_orders(message: Message, db: Database) -> None:
    text, keyboard = await order_list(db, message.from_user.id)
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data == 'my_orders')
@router.callback_query(F.data.startswith('own_orders:'))
async def cb_my_orders(call: CallbackQuery, db: Database) -> None:
    parts = call.data.split(':')
    history = len(parts) == 3 and parts[1] == 'all'
    page = (safe_int(parts[2]) or 0) if len(parts) == 3 else 0
    text, keyboard = await order_list(db, call.from_user.id, history=history, page=page)
    await replace_or_edit(call.message, text, keyboard)
    await call.answer()


def order_detail(order: OrderSummary):
    lines = [f'📦 <b>Заявка #{order.id}</b>', STATUS_LABELS.get(order.status, order.status), '']
    for item in order.items:
        price = f'{item.subtotal:.0f} ₽' if item.price else 'цена уточняется'
        lines.append(f'• {escape(item.name)} × {item.quantity} · {price}')
    label = 'Сумма известных цен' if any(not i.price for i in order.items) else 'Итого'
    lines.append(f'\n{label}: <b>{order.total:.0f} ₽</b>')
    builder = InlineKeyboardBuilder()
    if order.status == 'new':
        builder.button(text='Отменить заявку', callback_data=f'own_cancel_ask:{order.id}')
    builder.button(text='💬 Написать менеджеру', callback_data=f'order_chat:{order.id}')
    builder.button(text='← Активные заявки', callback_data='my_orders')
    builder.button(text='🗂 История', callback_data='own_orders:all:0')
    builder.adjust(1)
    return '\n'.join(lines), builder.as_markup()


async def owned_order(call: CallbackQuery, db: Database) -> OrderSummary | None:
    order_id = safe_int(call.data.partition(':')[2])
    order = await db.get_order(order_id) if order_id else None
    if not order or order.user_id != call.from_user.id:
        await call.answer('Заявка не найдена', show_alert=True)
        return None
    return order


@router.callback_query(F.data.startswith('own_order:'))
async def cb_own_order(call: CallbackQuery, db: Database) -> None:
    order = await owned_order(call, db)
    if not order:
        return
    text, keyboard = order_detail(order)
    await replace_or_edit(call.message, text, keyboard)
    await call.answer()


@router.callback_query(F.data.startswith('own_cancel_ask:'))
async def cb_cancel_ask(call: CallbackQuery, db: Database) -> None:
    order = await owned_order(call, db)
    if not order:
        return
    if order.status != 'new':
        await call.answer('Отмена доступна только для новой заявки. По другим статусам напишите менеджеру.', show_alert=True)
        return
    builder = InlineKeyboardBuilder()
    builder.button(text='Да, отменить', callback_data=f'own_cancel:{order.id}')
    builder.button(text='Оставить заявку', callback_data=f'own_order:{order.id}')
    builder.adjust(1)
    await replace_or_edit(call.message, f'Отменить заявку #{order.id}? Она останется в истории.', builder.as_markup())
    await call.answer()


@router.callback_query(F.data.startswith('own_cancel:'))
async def cb_cancel_order(call: CallbackQuery, db: Database, config: Config, bot: Bot) -> None:
    order = await owned_order(call, db)
    if not order:
        return
    ok, _ = await db.update_order_status(order.id, 'cancelled', changed_by=call.from_user.id,
                                         note='Отменено покупателем', expected_status='new')
    if not ok:
        await call.answer('Статус уже изменился. Обновите список заявок.', show_alert=True)
        return
    await replace_or_edit(call.message, f'✅ Заявка #{order.id} отменена и перенесена в историю.', navigation())
    await call.answer('Заявка отменена')
    if config.owner_chat_id:
        try:
            await bot.send_message(config.owner_chat_id,
                                   f'❌ <b>Покупатель отменил заявку #{order.id}</b>\n'
                                   f'{escape(order.full_name)}\nКарточка: /order {order.id}')
        except TelegramAPIError:
            log.warning('Cancellation notification failed for order %s', order.id)
