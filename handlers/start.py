"""/start, /help, the main menu, About screen, and deep-links."""
from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, KeyboardButton, Message, ReplyKeyboardMarkup, WebAppInfo

from config import Config
from database import Database
from keyboards.inline import main_menu_kb, product_kb
from utils.parsing import safe_int
from utils.telegram import replace_or_edit

router = Router(name="start")


WELCOME_TEXT = (
    "👋 <b>Добро пожаловать в «Дачу Сердюка»</b>\n\n"
    "Выберите вино в магазине, добавьте его в корзину и отправьте заявку.\n\n"
    "После заявки команда свяжется с вами для уточнения деталей."
)

ABOUT_TEXT = (
    "ℹ️ <b>О магазине «Дача Сердюка»</b>\n\n"
    "Каталог вин работает внутри Telegram. Оплата онлайн пока не подключена.\n\n"
    "После получения заявки команда свяжется с покупателем."
)


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject, db: Database, config: Config, state: FSMContext) -> None:
    """Show the main menu, or jump straight to a product if the user came in
    via a `?start=product_N` deep link from inline search."""
    await state.clear()
    arg = (command.args or "").strip()
    if arg.startswith("product_"):
        product_id = safe_int(arg[len("product_"):])
        if product_id is not None:
            product = await db.get_product(product_id)
            if product:
                from html import escape
                caption = (
                    f"<b>{escape(product.name)}</b>\n\n"
                    f"{escape(product.description)}\n\n"
                    f"💵 <b>{product.price:.0f} ₽</b>"
                )
                await message.answer(caption, reply_markup=product_kb(product))
                return
    await show_shop_menu(message, config, message.from_user.id)


async def show_shop_menu(message: Message, config: Config, user_id: int) -> None:
    if not config.webapp_url:
        await message.answer(WELCOME_TEXT, reply_markup=main_menu_kb())
        return
    if message.chat.type != "private":
        await message.answer("Откройте магазин в личном чате с ботом: /start.")
        return
    rows = [[KeyboardButton(text="🛍 Открыть магазин", web_app=WebAppInfo(url=config.webapp_url))],
            [KeyboardButton(text="📦 Мои заявки")],
            [KeyboardButton(text="🔄 Перезапустить магазин")]]
    if user_id in config.team_ids:
        rows.append([KeyboardButton(text="📋 Заказы команды")])
    await message.answer(WELCOME_TEXT, reply_markup=ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True))


@router.callback_query(F.data == "open_shop")
async def cb_open_shop(call: CallbackQuery, config: Config) -> None:
    await show_shop_menu(call.message, config, call.from_user.id)
    await call.answer()


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    text = (
        "<b>Available commands</b>\n"
        "/start — main menu\n"
        "/catalog — browse products\n"
        "/cart — view your cart\n"
        "/orders — your past orders\n"
        "/help — this message"
    )
    await message.answer(text)


@router.message(Command("restart"))
@router.message(F.text == "🔄 Перезапустить магазин")
async def restart_shop(message: Message, state: FSMContext, db: Database, config: Config) -> None:
    """Reset only this user's checkout state and cart, without restarting the bot."""
    await state.clear()
    await db.clear_cart(message.from_user.id)
    await message.answer(
        "🔄 Корзина бота и незавершённый ввод очищены.\n"
        "Сохранённые заявки остаются в «Мои заявки». Новую заявку можно отменить в её карточке."
    )
    await show_shop_menu(message, config, message.from_user.id)


@router.callback_query(F.data == "home")
async def cb_home(call: CallbackQuery) -> None:
    await replace_or_edit(call.message, WELCOME_TEXT, main_menu_kb())
    await call.answer()


@router.callback_query(F.data == "about")
async def cb_about(call: CallbackQuery) -> None:
    await replace_or_edit(call.message, ABOUT_TEXT, main_menu_kb())
    await call.answer()
