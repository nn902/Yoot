import os
import sqlite3
import asyncio
import logging
import threading
import aiohttp
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, PreCheckoutQuery, WebAppInfo, LabeledPrice
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# --- НАСТРОЙКИ ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "ТВОЙ_ТОКЕН_БОТА")
ADMIN_ID = 7727345054
# Сюда вставишь ссылку на твой сайт с Vercel (например: https://nm-cinema.vercel.app)
WEBAPP_URL = "https://example.com" 

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
router = Router()
logging.basicConfig(level=logging.INFO)

# ==============================================================================
# ✨ ПРЕМИУМ ЭМОДЗИ
# ==============================================================================
E_FIRE   = '<tg-emoji emoji-id="5801004944211317728">🔥</tg-emoji>'
E_STAR   = '<tg-emoji emoji-id="5438496463044752972">⭐️</tg-emoji>'
E_MONEY  = '<tg-emoji emoji-id="5373001317042101552">💰</tg-emoji>'
E_USER   = '<tg-emoji emoji-id="5841276284155467413">👤</tg-emoji>'
E_GEAR   = '<tg-emoji emoji-id="5373012449597335010">⚙️</tg-emoji>'
E_SEARCH = '<tg-emoji emoji-id="5199750217586459631">📄</tg-emoji>'
E_FILM   = '<tg-emoji emoji-id="5278702045883292456">🏪</tg-emoji>'
E_CHECK  = '<tg-emoji emoji-id="5206607081334906820">✔️</tg-emoji>'
E_CROSS  = '<tg-emoji emoji-id="5274099962655816924">❗️</tg-emoji>'
E_ROCKET = '<tg-emoji emoji-id="5780773956030043338">🚀</tg-emoji>'

# ==============================================================================
# 🗄 БАЗА ДАННЫХ
# ==============================================================================
DB_FILE = "cinema.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # Добавили image_url для картинок
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            balance REAL DEFAULT 0.0,
            referrer_id INTEGER,
            ref_count INTEGER DEFAULT 0,
            watch_time INTEGER DEFAULT 0
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS movies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            category TEXT,
            file_id TEXT,
            image_url TEXT,
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
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS favorites (
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
# 🧠 СОСТОЯНИЯ (FSM)
# ==============================================================================
class AddMovie(StatesGroup):
    title = State()
    category = State()
    video = State()
    image = State()
    price = State()

class SearchMovie(StatesGroup):
    query = State()

CATEGORIES = ["Мультфильмы", "Фильмы", "Сериалы", "Аниме", "Боевик", "Комедия", "Ужасы", "Фантастика", "Драма"]

# ==============================================================================
# 👤 БОТ
# ==============================================================================
def get_main_kb(user_id):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🍿 Открыть Кинотеатр (Mini App)", web_app=WebAppInfo(url=WEBAPP_URL), style="success")],
        [InlineKeyboardButton(text="🔍 Поиск фильма", callback_data="search_start", style="primary")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile", style="primary")]
    ])
    if user_id == ADMIN_ID:
        kb.inline_keyboard.append([InlineKeyboardButton(text="⚙️ Админ-панель", callback_data="admin_panel", style="danger")])
    return kb

@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject = None):
    user_id = message.from_user.id
    args = command.args if command else None
    
    ref_id = None
    if args and args.startswith("ref_"):
        try:
            ref_id = int(args.split("_")[1])
            if ref_id == user_id: ref_id = None
        except: pass

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

    await message.answer(
        f"{E_FIRE} <b>Добро пожаловать в наш Кинотеатр!</b>\n\n"
        f"Здесь ты найдешь лучшие мультики и фильмы. {E_ROCKET}\n"
        f"Открывай Mini App или ищи фильмы прямо здесь!",
        reply_markup=get_main_kb(user_id)
    )

@router.callback_query(F.data == "profile")
async def show_profile(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    user_id, username, first_name, balance, referrer_id, ref_count, watch_time = user
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"

    text = (
        f"{E_USER} <b>Твой профиль</b>\n\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"👤 Имя: {first_name}\n"
        f"🔗 Юзернейм: @{username if username else 'Нет'}\n\n"
        f"{E_MONEY} <b>Баланс:</b> {balance} баллов (1 ⭐️ = 1.5 балла)\n"
        f"👥 <b>Приглашено друзей:</b> {ref_count}\n\n"
        f"<i>Твоя реферальная ссылка:</i>\n<code>{ref_link}</code>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main", style="danger")]])
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(f"{E_FIRE} <b>Главное меню</b>", reply_markup=get_main_kb(callback.from_user.id))
    await callback.answer()

@router.callback_query(F.data == "search_start")
async def search_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SearchMovie.query)
    await callback.message.edit_text(
        f"{E_SEARCH} <b>Введите название фильма или категорию:</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="back_to_main", style="danger")]])
    )
    await callback.answer()

@router.message(SearchMovie.query)
async def search_process(message: Message, state: FSMContext):
    await state.clear()
    query = f"%{message.text.strip()}%"
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, category, price FROM movies WHERE title LIKE ? OR category LIKE ? LIMIT 10", (query, query))
    movies = cursor.fetchall()
    conn.close()

    if not movies:
        return await message.answer(f"{E_CROSS} Ничего не найдено.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main", style="danger")]]))

    await message.answer(f"{E_SEARCH} <b>Результаты поиска:</b>")
    for m in movies:
        m_id, title, category, price = m
        if price == 0:
            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🎬 Смотреть бесплатно", callback_data=f"watch_{m_id}", style="success")]])
            await message.answer(f"🎬 <b>{title}</b>\n📁 {category}\n🆓 <b>Бесплатно</b>", reply_markup=kb)
        else:
            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"Купить за {price} ⭐️", callback_data=f"buy_{m_id}_{price}", style="success")]])
            await message.answer(f"🎬 <b>{title}</b>\n📁 {category}\n💰 {price} ⭐️", reply_markup=kb)

@router.callback_query(F.data.startswith("buy_"))
async def buy_movie(callback: CallbackQuery):
    _, m_id, price = callback.data.split("_")
    await bot.send_invoice(chat_id=callback.message.chat.id, title="Покупка фильма", description="Доступ навсегда", payload=f"movie_{m_id}", provider_token="", currency="XTR", prices=[LabeledPrice(label="Фильм", amount=int(price))])
    await callback.answer()

@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)

@router.message(F.successful_payment)
async def process_successful_payment(message: Message):
    payload = message.successful_payment.invoice_payload
    if payload.startswith("movie_"):
        m_id = int(payload.split("_")[1])
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO purchases (user_id, movie_id) VALUES (?, ?)", (message.from_user.id, m_id))
        cursor.execute("SELECT title, file_id FROM movies WHERE id = ?", (m_id,))
        movie = cursor.fetchone()
        conn.commit()
        conn.close()
        await message.answer(f"{E_CHECK} <b>Оплата прошла успешно!</b>")
        await message.answer_video(video=movie[1], caption=f"🎬 <b>{movie[0]}</b>")

@router.callback_query(F.data.startswith("watch_"))
async def watch_movie(callback: CallbackQuery):
    m_id = int(callback.data.split("_")[1])
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO purchases (user_id, movie_id) VALUES (?, ?)", (callback.from_user.id, m_id))
    cursor.execute("SELECT title, file_id FROM movies WHERE id = ?", (m_id,))
    movie = cursor.fetchone()
    conn.commit()
    conn.close()
    if movie:
        await callback.message.answer_video(video=movie[1], caption=f"🎬 <b>{movie[0]}</b>")
        await callback.answer()

# ==============================================================================
# ⚙️ АДМИН-ПАНЕЛЬ (Добавили картинки)
# ==============================================================================
@router.callback_query(F.data == "admin_panel")
async def admin_panel(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID: return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить фильм", callback_data="add_movie", style="success")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main", style="danger")]
    ])
    await callback.message.edit_text(f"{E_GEAR} <b>Админ-панель</b>", reply_markup=kb)
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
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=c, callback_data=f"cat_{c}", style="primary")] for c in CATEGORIES])
    await message.answer("2️⃣ Выбери категорию:", reply_markup=kb)

@router.callback_query(AddMovie.category, F.data.startswith("cat_"))
async def process_category(callback: CallbackQuery, state: FSMContext):
    cat = callback.data.replace("cat_", "")
    await state.update_data(category=cat)
    await state.set_state(AddMovie.video)
    await callback.message.edit_text(f"Категория: <b>{cat}</b>")
    await callback.message.answer("3️⃣ Отправь видео-файл (перешли из канала):")
    await callback.answer()

@router.message(AddMovie.video, F.video)
async def process_video(message: Message, state: FSMContext):
    await state.update_data(file_id=message.video.file_id)
    await state.set_state(AddMovie.image)
    await message.answer("4️⃣ Отправь картинку-обложку (или напиши 'нет', и сайт сгенерирует её сам):")

@router.message(AddMovie.image)
async def process_image(message: Message, state: FSMContext):
    if message.photo:
        img_url = message.photo[-1].file_id # Пока сохраняем file_id картинки
    else:
        img_url = "generated" # Сайт сам нарисует обложку
    
    await state.update_data(image_url=img_url)
    await state.set_state(AddMovie.price)
    await message.answer("5️⃣ Введи цену в Звездах (0 - если бесплатно):")

@router.message(AddMovie.price)
async def process_price(message: Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("Введи только число!")
    
    price = int(message.text)
    data = await state.get_data()
    await state.clear()

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO movies (title, category, file_id, image_url, price) VALUES (?, ?, ?, ?, ?)",
                   (data['title'], data['category'], data['file_id'], data['image_url'], price))
    conn.commit()
    
    cursor.execute("SELECT user_id FROM users")
    users = [row[0] for row in cursor.fetchall()]
    conn.close()

    await message.answer(f"{E_CHECK} Фильм <b>{data['title']}</b> добавлен! Рассылка пошла...", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 В админку", callback_data="admin_panel")]]))

    price_text = f"{E_MONEY} Цена: {price} ⭐️" if price > 0 else "🆓 <b>Бесплатно</b>"
    broadcast_text = f"{E_FIRE} <b>НОВЫЙ УНИКАЛЬНЫЙ ФИЛЬМ!</b> {E_FIRE}\n\n🎬 <b>{data['title']}</b>\n📁 {data['category']}\n{price_text}\n\nСкорее заходи в бота и смотри!"
    
    async def send_broadcast():
        for u_id in users:
            try:
                await bot.send_message(u_id, broadcast_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🍿 В кинотеатр", callback_data="back_to_main", style="success")]]))
                await asyncio.sleep(0.05)
            except: pass
    asyncio.create_task(send_broadcast())

# ==============================================================================
# 🌐 API ДЛЯ САЙТА (Vercel)
# ==============================================================================
api = FastAPI()
api.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@api.get("/api/movies")
def get_movies():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, category, price, image_url FROM movies")
    movies = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return {"movies": movies}

@api.get("/api/user/{user_id}")
def get_user_profile(user_id: int):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT first_name, username, balance, ref_count, watch_time FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    
    cursor.execute("SELECT COUNT(*) FROM purchases WHERE user_id = ?", (user_id,))
    movies_bought = cursor.fetchone()[0]
    conn.close()
    
    if user:
        return {
            "first_name": user[0], "username": user[1], "balance": user[2], 
            "ref_count": user[3], "watch_time": user[4], "movies_bought": movies_bought
        }
    return {"error": "User not found"}

@api.get("/api/user/{user_id}/movies")
def get_user_movies(user_id: int):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT m.id, m.title, m.category, m.price, m.image_url 
        FROM purchases p JOIN movies m ON p.movie_id = m.id 
        WHERE p.user_id = ?
    """, (user_id,))
    movies = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return {"movies": movies}

# ==============================================================================
# 🚀 ЗАПУСК
# ==============================================================================
def run_web_server():
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(api, host="0.0.0.0", port=port, log_level="warning")

async def main():
    init_db()
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    threading.Thread(target=run_web_server, daemon=True).start()
    logging.info("🚀 Бот и API запущены!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
