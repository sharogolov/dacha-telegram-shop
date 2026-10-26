"""Order messages between the manager/team and customer, including no username."""
from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import Config
from database import Database
from utils.parsing import safe_int

router = Router(name='order_chat')
router.message.filter(F.chat.type == 'private')
router.callback_query.filter(F.message.chat.type == 'private')


class OrderChat(StatesGroup):
    text = State()


def reply_keyboard(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text='💬 Ответить по заявке', callback_data=f'order_chat:{order_id}')
    ]])


@router.callback_query(F.data.startswith('order_chat:'))
async def start_order_chat(call: CallbackQuery, state: FSMContext, db: Database, config: Config) -> None:
    order_id = safe_int(call.data.partition(':')[2])
    order = await db.get_order(order_id) if order_id else None
    if not order or (call.from_user.id != order.user_id and call.from_user.id not in config.team_ids):
        await call.answer('Нет доступа к заявке', show_alert=True)
        return
    if call.from_user.id not in config.team_ids and not config.owner_chat_id:
        await call.answer('Менеджер пока не настроен', show_alert=True)
        return
    await state.clear()
    await state.set_state(OrderChat.text)
    await state.update_data(order_chat_id=order.id)
    await call.message.answer(f'Напишите сообщение по заявке #{order.id}. Отправлю его через бота.\nОтмена: /cancel')
    await call.answer()


@router.message(OrderChat.text, F.text == '/cancel')
async def cancel_order_chat(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer('Отправка сообщения отменена.')


@router.message(OrderChat.text, F.text, ~F.text.startswith('/'),
                ~F.text.in_({'📦 Мои заявки', '📋 Заказы команды'}))
async def send_order_chat(message: Message, state: FSMContext, db: Database, config: Config, bot: Bot) -> None:
    data = await state.get_data()
    order = await db.get_order(data['order_chat_id'])
    is_team = message.from_user.id in config.team_ids
    if not order or (not is_team and message.from_user.id != order.user_id):
        await state.clear()
        await message.answer('Нет доступа к заявке.')
        return
    text = message.text.strip()
    if not 1 <= len(text) <= 1800:
        await message.answer('Отправьте текст до 1800 символов.')
        return
    target = order.user_id if is_team else config.owner_chat_id
    if not target:
        await message.answer('Менеджер пока не настроен. Попробуйте позже.')
        return
    sender = 'Команда магазина' if is_team else 'Покупатель'
    try:
        await bot.send_message(
            target, f'💬 <b>{sender} · заявка #{order.id}</b>\n\n{escape(text)}',
            reply_markup=reply_keyboard(order.id),
        )
    except TelegramAPIError:
        await message.answer('Не удалось доставить сообщение. Попробуйте позже или /cancel.')
        return
    await state.clear()
    await message.answer('Сообщение доставлено.')
