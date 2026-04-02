import asyncio
import html
import logging
import os
from typing import Any, Dict, List, Optional

import aiohttp
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

# ==============================
# CONFIG
# ==============================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8231512767:AAFERPmBkIXeSTR92VvrOIcKVPduChoGJOs")
RAWG_API_KEY = os.getenv("RAWG_API_KEY", "a547879680a64bf9a9910e9bddb78c0b")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = Router()

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🎮 O'yin qidiruv")],
        [KeyboardButton(text="🎵 Musiqa")],
        [KeyboardButton(text="🏠 Bosh menu")],
    ],
    resize_keyboard=True,
)

class SearchStates(StatesGroup):
    waiting_for_game = State()
    waiting_for_music = State()

# ==============================
# HELPERS
# ==============================
def safe_text(value: Optional[str], fallback: str = "-") -> str:
    if value is None or value == "":
        return fallback
    return html.escape(str(value))

def cut_text(text: Optional[str], length: int = 350) -> str:
    if not text:
        return "Ma'lumot topilmadi."
    text = text.strip().replace("\r", " ").replace("\n\n", "\n")
    return text[:length] + ("..." if len(text) > length else "")

def translate_term(value: str) -> str:
    mapping = {
        "Action": "Aksiya",
        "Adventure": "Sarguzasht",
        "RPG": "Rol o'yini",
        "Role-Playing Games (RPG)": "Rol o'yini",
        "Shooter": "Otishma",
        "Puzzle": "Boshqotirma",
        "Racing": "Poyga",
        "Sports": "Sport",
        "Strategy": "Strategiya",
        "Simulation": "Simulyatsiya",
        "Arcade": "Arkad",
        "Fighting": "Jang",
        "Casual": "Oddiy",
        "Indie": "Indi",
        "Massively Multiplayer": "Ko'p o'yinchili",
        "PC": "Kompyuter",
        "PlayStation 5": "PlayStation 5",
        "PlayStation 4": "PlayStation 4",
        "Xbox One": "Xbox One",
        "Xbox Series S/X": "Xbox Series S/X",
        "Nintendo Switch": "Nintendo Switch",
        "Android": "Android",
        "iOS": "iPhone",
        "Linux": "Linux",
        "macOS": "macOS",
        "Steam": "Steam",
        "Epic Games": "Epic Games",
        "GOG": "GOG",
        "PlayStation Store": "PlayStation do'koni",
        "Xbox Store": "Xbox do'koni",
        "App Store": "App Store",
        "Google Play": "Google Play",
    }
    return mapping.get(value, value)

def translate_items(values: List[str]) -> str:
    if not values:
        return "-"
    return ", ".join(translate_term(v) for v in values)

async def fetch_json(
    session: aiohttp.ClientSession,
    url: str,
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as response:
        response.raise_for_status()
        return await response.json()

async def search_games(query: str) -> List[Dict[str, Any]]:
    url = "https://api.rawg.io/api/games"
    params = {
        "key": RAWG_API_KEY,
        "search": query,
        "page_size": 5,
    }

    async with aiohttp.ClientSession() as session:
        data = await fetch_json(session, url, params)
        return data.get("results", [])

async def get_game_details(game_id: int) -> Dict[str, Any]:
    async with aiohttp.ClientSession() as session:
        details = await fetch_json(
            session,
            f"https://api.rawg.io/api/games/{game_id}",
            {"key": RAWG_API_KEY},
        )

        screenshots = await fetch_json(
            session,
            f"https://api.rawg.io/api/games/{game_id}/screenshots",
            {"key": RAWG_API_KEY},
        )

        movies = await fetch_json(
            session,
            f"https://api.rawg.io/api/games/{game_id}/movies",
            {"key": RAWG_API_KEY},
        )

        details["screenshots"] = screenshots.get("results", [])
        details["movies"] = movies.get("results", [])
        return details

async def search_music(query: str) -> List[Dict[str, Any]]:
    url = "https://itunes.apple.com/search"
    params = {
        "term": query,
        "media": "music",
        "entity": "song",
        "limit": 10,
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as response:
            response.raise_for_status()
            data = await response.json(content_type=None)
            return data.get("results", [])

def build_music_buttons(items: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    rows = []
    for index, item in enumerate(items):
        track = item.get("trackName", "Noma'lum")
        artist = item.get("artistName", "Noma'lum")
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{index + 1}. {track} — {artist}",
                    callback_data=f"music_{index}",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)

def build_game_buttons(game: Dict[str, Any]) -> InlineKeyboardMarkup:
    buttons = []

    website = game.get("website")
    reddit = game.get("reddit_url")

    if website:
        buttons.append([InlineKeyboardButton(text="🌐 Rasmiy sayt", url=website)])
    if reddit:
        buttons.append([InlineKeyboardButton(text="💬 Reddit", url=reddit)])

    if not buttons:
        buttons.append([InlineKeyboardButton(text="ℹ️ Qo'shimcha havola topilmadi", callback_data="noop")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)

def format_game_caption(game: Dict[str, Any]) -> str:
    genres_list = [g.get("name", "") for g in game.get("genres", [])[:3] if g.get("name")]
    platforms_list = [
        p.get("platform", {}).get("name", "")
        for p in game.get("platforms", [])[:4]
        if p.get("platform", {}).get("name")
    ]
    stores_list = [
        s.get("store", {}).get("name", "")
        for s in game.get("stores", [])[:3]
        if s.get("store", {}).get("name")
    ]

    description = cut_text(game.get("description_raw"), 350)

    return (
        f"<b>🎮 O'yin:</b> {safe_text(game.get('name'))}\n"
        f"<b>📅 Chiqqan sana:</b> {safe_text(game.get('released'))}\n"
        f"<b>⭐ Reyting:</b> {safe_text(game.get('rating'))}\n"
        f"<b>🏆 Metacritic:</b> {safe_text(game.get('metacritic'))}\n"
        f"<b>🎯 Janr:</b> {safe_text(translate_items(genres_list))}\n"
        f"<b>🕹 Platforma:</b> {safe_text(translate_items(platforms_list))}\n"
        f"<b>🛒 Do'kon:</b> {safe_text(translate_items(stores_list))}\n\n"
        f"<b>📝 Qisqacha ma'lumot:</b>\n{safe_text(description)}"
    )

# ==============================
# START / MENU
# ==============================
@router.message(CommandStart())
async def start_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    text = (
        "<b>Assalomu alaykum, Reflex Game Bot ga xush kelibsiz!</b>\n\n"
        "Kerakli bo'limni tanlang:\n"
        "🎮 O'yin qidiruv — o'yin haqida ma'lumot, rasm va trailer\n"
        "🎵 Musiqa — top 10 natija va preview audio"
    )
    await message.answer(text, reply_markup=MAIN_KEYBOARD)

@router.message(F.text == "🏠 Bosh menu")
async def menu_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Bosh menuga qaytdingiz.", reply_markup=MAIN_KEYBOARD)

@router.message(F.text == "🎮 O'yin qidiruv")
async def game_menu_handler(message: Message, state: FSMContext) -> None:
    await state.set_state(SearchStates.waiting_for_game)
    await message.answer("Iltimos, biron bir o'yin nomini kiriting:")

@router.message(F.text == "🎵 Musiqa")
async def music_menu_handler(message: Message, state: FSMContext) -> None:
    await state.set_state(SearchStates.waiting_for_music)
    await message.answer("Iltimos, biron bir musiqa nomini yozing:")

# ==============================
# GAME SEARCH
# ==============================
@router.message(SearchStates.waiting_for_game)
async def game_search_handler(message: Message, state: FSMContext) -> None:
    query = (message.text or "").strip()

    if not query:
        await message.answer("Iltimos, o'yin nomini yozing.")
        return

    if query == "🏠 Bosh menu":
        await state.clear()
        await message.answer("Bosh menuga qaytdingiz.", reply_markup=MAIN_KEYBOARD)
        return

    if RAWG_API_KEY == "BU_YERGA_YANGI_RAWG_API_KEY":
        await message.answer("RAWG API key kiritilmagan.")
        return

    wait_msg = await message.answer("Qidirilmoqda...")

    try:
        games = await search_games(query)
        if not games:
            await wait_msg.edit_text("Bu nom bo'yicha o'yin topilmadi. Yana boshqa o'yin nomini yozishingiz mumkin.")
            return

        best = games[0]
        full = await get_game_details(best["id"])

        screenshots = full.get("screenshots", [])[:3]
        image_urls: List[str] = []

        if full.get("background_image"):
            image_urls.append(full["background_image"])

        for shot in screenshots:
            if shot.get("image"):
                image_urls.append(shot["image"])

        caption = format_game_caption(full)
        keyboard = build_game_buttons(full)

        if image_urls:
            await message.answer_photo(
                photo=image_urls[0],
                caption=caption,
                reply_markup=keyboard,
            )

            extra_images = image_urls[1:4]
            if extra_images:
                media_group = [InputMediaPhoto(media=url) for url in extra_images]
                await message.answer_media_group(media=media_group)
        else:
            await message.answer(caption, reply_markup=keyboard)

        movies = full.get("movies", [])
        if movies:
            movie = movies[0]
            video_url = (
                movie.get("data", {}).get("max")
                or movie.get("data", {}).get("480")
                or movie.get("preview")
            )
            if video_url:
                try:
                    await message.answer_video(
                        video=video_url,
                        caption=f"🎬 {safe_text(full.get('name'))} traileri",
                    )
                except Exception:
                    trailer_keyboard = InlineKeyboardMarkup(
                        inline_keyboard=[
                            [InlineKeyboardButton(text="▶️ Trailer ochish", url=video_url)]
                        ]
                    )
                    await message.answer(
                        "Trailer videoni to'g'ridan-to'g'ri yuborib bo'lmadi. Tugma orqali oching.",
                        reply_markup=trailer_keyboard,
                    )
        else:
            await message.answer("Bu o'yin uchun trailer topilmadi.")

        await wait_msg.delete()
        await message.answer("Yana o'yin qidirish uchun boshqa o'yin nomini yozavering.")

    except aiohttp.ClientResponseError as error:
        logger.exception("Game search HTTP error: %s", error)
        if error.status in (401, 403):
            await wait_msg.edit_text("RAWG API key noto'g'ri yoki ishlamayapti.")
        elif error.status == 404:
            await wait_msg.edit_text("Bu o'yin bo'yicha ma'lumot topilmadi.")
        else:
            await wait_msg.edit_text(f"Server xatoligi yuz berdi: {error.status}")
    except Exception as error:
        logger.exception("Game search error: %s", error)
        await wait_msg.edit_text(f"Xatolik yuz berdi: {html.escape(str(error))}")

# ==============================
# MUSIC SEARCH
# ==============================
@router.message(SearchStates.waiting_for_music)
async def music_search_handler(message: Message, state: FSMContext) -> None:
    query = (message.text or "").strip()

    if not query:
        await message.answer("Iltimos, musiqa nomini yozing.")
        return

    if query == "🏠 Bosh menu":
        await state.clear()
        await message.answer("Bosh menuga qaytdingiz.", reply_markup=MAIN_KEYBOARD)
        return

    wait_msg = await message.answer("Musiqalar qidirilmoqda...")

    try:
        results = await search_music(query)

        filtered = []
        for item in results:
            if item.get("previewUrl") and item.get("trackName"):
                filtered.append(item)

        filtered = filtered[:10]

        if not filtered:
            await wait_msg.edit_text("Bu nom bo'yicha musiqa topilmadi. Yana boshqa nom yozing.")
            return

        await state.update_data(music_results=filtered)

        keyboard = build_music_buttons(filtered)

        await wait_msg.edit_text(
            "Quyidagi musiqalardan birini tanlang:",
            reply_markup=keyboard
        )

    except Exception as error:
        logger.exception("Music search error: %s", error)
        await wait_msg.edit_text(f"Musiqa qidirishda xatolik: {str(error)}")

@router.callback_query(F.data.startswith("music_"))
async def music_pick_handler(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    results = data.get("music_results", [])

    try:
        index = int((callback.data or "").split("_")[1])
    except Exception:
        await callback.answer("Noto'g'ri tanlov", show_alert=True)
        return

    if index < 0 or index >= len(results):
        await callback.answer("Natija topilmadi", show_alert=True)
        return

    item = results[index]
    track = item.get("trackName", "Noma'lum")
    artist = item.get("artistName", "Noma'lum")
    album = item.get("collectionName", "-")
    preview_url = item.get("previewUrl")
    artwork = item.get("artworkUrl100")

    if artwork:
        artwork = artwork.replace("100x100bb", "600x600bb")

    caption = (
        f"<b>{safe_text(track)}</b>\n"
        f"<b>Ijrochi:</b> {safe_text(artist)}\n"
        f"<b>Albom:</b> {safe_text(album)}\n"
        f"<b>Preview:</b> 30 soniyalik namuna"
    )

    try:
        if callback.message:
            if artwork:
                await callback.message.answer_photo(photo=artwork, caption=caption)
            else:
                await callback.message.answer(caption)

            await callback.message.answer_audio(
                audio=preview_url,
                title=track,
                performer=artist
            )

            await callback.message.answer("Yana musiqa qidirish uchun boshqa musiqa nomini yozavering.")

        await callback.answer("Yuborildi")

    except Exception as error:
        logger.exception("Send music error: %s", error)
        await callback.answer(f"Audio yuborishda xatolik: {str(error)}", show_alert=True)

@router.callback_query(F.data == "noop")
async def noop_handler(callback: CallbackQuery) -> None:
    await callback.answer()

# ==============================
# MAIN
# ==============================
async def main() -> None:
    if BOT_TOKEN == "BU_YERGA_YANGI_BOT_TOKEN":
        raise ValueError("BOT_TOKEN ni kiriting")

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dispatcher = Dispatcher()
    dispatcher.include_router(router)

    logger.info("Bot ishga tushdi...")
    await dispatcher.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())