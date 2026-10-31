import os
import sqlite3
import asyncio
import logging
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice, PreCheckoutQuery, WebAppInfo
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

# --- НАСТРОЙКИ ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "ТВОЙ_ТОКЕН")
ADMIN_ID = 7727345054
# Ссылка на твой будущий Mini App (пока поставим заглушку)
WEBAPP_URL = "https://example.com" 

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
router = Router()
logging.basicConfig(level=logging.INFO)

# ==============================================================================
# ✨ ЭМОДЗИ
# ==============================================================================
E_STAR = '<tg-emoji emoji-id="5438496463044752972">⭐️</tg-emoji>'
E_FIRE = '<tg-emoji emoji-id="5801004944211317728">🔥</tg-emoji>'
E_USER = '<tg-emoji emoji-id="5841276284155467413">👤</tg-emoji>'
E_MONEY = '<tg-emoji emoji-id="5373001317042101552">💰</tg-emoji>'
E_GEAR = '<tg-emoji emoji-id="5373012449597335010">⚙️</tg-emoji>'
E_CHECK = '<tg-emoji emoji-id="5206607081334906820">✔️</tg-emoji>'

# ==============================================================================
# 🗄 БАЗА ДАННЫХ
# ==============================================================================
DB_FILE = "cinema.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # Пользователи
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            balance REAL DEFAULT 0.0,
            referrer_id INTEGER,
            ref_count INTEGER DEFAULT 0
        )
    """)
    # Фильмы
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS movies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            category TEXT,
            file_id TEXT,
            price INTEGER DEFAULT 19
        )
    """)
    # Покупки
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS purchases (
            user_id INTEGER,
            movie_id INTEGER,
            PRIMARY KEY (user_id, movie_id)
        )
    """)
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row

# ==============================================================================
# 🧠 СОСТОЯНИЯ (FSM) ДЛЯ АДМИНКИ
# ==============================================================================
class AddMovie(StatesGroup):
    title = State()
    category = State()
    video = State()
    price = State()

# ==============================================================================
# 👤 ПОЛЬЗОВАТЕЛЬСКАЯ ЧАСТЬ
# ==============================================================================
@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject = None):
    user_id = message.from_user.id
    args = command.args if command else None
    
    ref_id = None
    if args and args.startswith("ref_"):
        try:
            ref_id = int(args.split("_")[1])
            if ref_id == user_id:
                ref_id = None
        except:
            pass

    user = get_user(user_id)
    if not user:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (user_id, username, first_name, referrer_id) VALUES (?, ?, ?, ?)",
                       (user_id, message.from_user.username, message.from_user.first_name, ref_id))
        if ref_id:
            # Начисляем бонус рефереру (например, 1 звезду в баланс)
            cursor.execute("UPDATE users SET ref_count = ref_count + 1, balance = balance + 1.5 WHERE user_id = ?", (ref_id,))
        conn.commit()
        conn.close()

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🍿 Открыть Кинотеатр (Mini App)", web_app=WebAppInfo(url=WEBAPP_URL))],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile")]
    ])
    
    if user_id == ADMIN_ID:
        kb.inline_keyboard.append([InlineKeyboardButton(text="⚙️ Админ-панель", callback_data="admin_panel")])

    await message.answer(
        f"{E_FIRE} <b>Добро пожаловать в наш Кинотеатр!</b>\n\n"
        f"Здесь ты найдешь лучшие мультики и фильмы.\n"
        f"Открывай Mini App, выбирай фильм и смотри с удовольствием!",
        reply_markup=kb
    )

@router.callback_query(F.data == "profile")
async def show_profile(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    if not user:
        return await callback.answer("Ошибка профиля", show_alert=True)
        
    user_id, username, first_name, balance, referrer_id, ref_count = user
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"

    text = (
        f"{E_USER} <b>Твой профиль</b>\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"👤 Имя: {first_name}\n"
        f"🔗 Юзернейм: @{username if username else 'Нет'}\n\n"
        f"{E_MONEY} <b>Баланс:</b> {balance} баллов (1 ⭐️ = 1.5 балла)\n"
        f"👥 <b>Приглашено друзей:</b> {ref_count}\n\n"
        f"<i>Твоя реферальная ссылка:</i>\n<code>{ref_link}</code>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🍿 Открыть Кинотеатр (Mini App)", web_app=WebAppInfo(url=WEBAPP_URL))],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile")]
    ])
    if callback.from_user.id == ADMIN_ID:
        kb.inline_keyboard.append([InlineKeyboardButton(text="⚙️ Админ-панель", callback_data="admin_panel")])
        
    await callback.message.edit_text(f"{E_FIRE} <b>Главное меню</b>", reply_markup=kb)
    await callback.answer()

# --- ОПЛАТА ЗВЕЗДАМИ (Пока для теста покупки) ---
@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)

@router.message(F.successful_payment)
async def process_successful_payment(message: Message):
    await message.answer(f"{E_CHECK} Оплата прошла успешно! Доступ к фильму открыт.")

# ==============================================================================
# ⚙️ АДМИН-ПАНЕЛЬ
# ==============================================================================
@router.callback_query(F.data == "admin_panel")
async def admin_panel(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID: return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить фильм", callback_data="add_movie", style="success")],
        [InlineKeyboardButton(text="📢 Сделать рассылку", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main", style="danger")]
    ])
    await callback.message.edit_text(f"{E_GEAR} <b>Админ-панель</b>\nВыбери действие:", reply_markup=kb)
    await callback.answer()

# --- ДОБАВЛЕНИЕ ФИЛЬМА (FSM) ---
@router.callback_query(F.data == "add_movie")
async def add_movie_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID: return
    await state.set_state(AddMovie.title)
    await callback.message.edit_text("1️⃣ Введи название фильма:")
    await callback.answer()

@router.message(AddMovie.title)
async def process_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text)
    await state.set_state(AddMovie.category)
    await message.answer("2️⃣ Введи категорию (например: Мультики, Боевик, Комедия):")

@router.message(AddMovie.category)
async def process_category(message: Message, state: FSMContext):
    await state.update_data(category=message.text)
    await state.set_state(AddMovie.video)
    await message.answer("3️⃣ Отправь видео-файл фильма (загрузи прямо в чат):")

@router.message(AddMovie.video, F.video)
async def process_video(message: Message, state: FSMContext):
    await state.update_data(file_id=message.video.file_id)
    await state.set_state(AddMovie.price)
    await message.answer("4️⃣ Введи цену в Звездах (например: 19):")

@router.message(AddMovie.price)
async def process_price(message: Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("Введи только число!")
    
    price = int(message.text)
    data = await state.get_data()
    await state.clear()

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO movies (title, category, file_id, price) VALUES (?, ?, ?, ?)",
                   (data['title'], data['category'], data['file_id'], price))
    conn.commit()
    conn.close()

    await message.answer(f"{E_CHECK} Фильм <b>{data['title']}</b> успешно добавлен в базу!", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 В админку", callback_data="admin_panel")]]))

# ==============================================================================
# 🚀 ЗАПУСК
# ==============================================================================
async def main():
    init_db()
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    print("🚀 Бот Кинотеатр запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
