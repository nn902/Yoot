import os
import sqlite3
import asyncio
import logging
import threading
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, PreCheckoutQuery, WebAppInfo
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# --- НАСТРОЙКИ ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "ТВОЙ_ТОКЕН_БОТА")
ADMIN_ID = 7727345054
WEBAPP_URL = "https://example.com" # Сюда потом вставишь ссылку с Vercel

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
router = Router()
logging.basicConfig(level=logging.INFO)

# --- БАЗА ДАННЫХ ---
DB_FILE = "cinema.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
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
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS movies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            category TEXT,
            file_id TEXT,
            price INTEGER DEFAULT 19
        )
    """)
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

# --- СОСТОЯНИЯ ---
class AddMovie(StatesGroup):
    title = State()
    category = State()
    video = State()
    price = State()

# --- ХЕНДЛЕРЫ БОТА ---
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
        "🔥 <b>Добро пожаловать в наш Кинотеатр!</b>\n\n"
        "Здесь ты найдешь лучшие мультики и фильмы.\n"
        "Открывай Mini App, выбирай фильм и смотри с удовольствием!",
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
        f"👤 <b>Твой профиль</b>\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"👤 Имя: {first_name}\n"
        f"🔗 Юзернейм: @{username if username else 'Нет'}\n\n"
        f"💰 <b>Баланс:</b> {balance} баллов (1 ⭐️ = 1.5 балла)\n"
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
        
    await callback.message.edit_text("🔥 <b>Главное меню</b>", reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data == "admin_panel")
async def admin_panel(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID: return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить фильм", callback_data="add_movie", style="success")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main", style="danger")]
    ])
    await callback.message.edit_text("⚙️ <b>Админ-панель</b>\nВыбери действие:", reply_markup=kb)
    await callback.answer()

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
    await message.answer("2️⃣ Введи категорию (например: Мультики, Боевик):")

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

    await message.answer(f"✅ Фильм <b>{data['title']}</b> успешно добавлен!", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 В админку", callback_data="admin_panel")]]))

# --- API ДЛЯ VERCEL ---
api = FastAPI()
api.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@api.get("/api/movies")
def get_movies():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, category, price FROM movies")
    movies = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return {"movies": movies}

# --- ЗАПУСК ВСЕГО ВМЕСТЕ ---
def run_web_server():
    # Амвера по умолчанию использует порт 80, но для внутреннего uvicorn лучше взять 8000
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(api, host="0.0.0.0", port=port, log_level="warning")

async def main():
    init_db()
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    
    # Запускаем веб-сервер в фоне
    threading.Thread(target=run_web_server, daemon=True).start()
    
    logging.info("🚀 Бот и API запущены!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
