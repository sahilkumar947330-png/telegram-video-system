import os
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command

from database import (
    init_db,
    save_content,
    save_file,
    get_content_by_token,
    get_files_for_content,
    search_contents,
)

# =============================
# CONFIG (ENV VARIABLES)
# =============================

COBRA_TOKEN = os.getenv("8218309579:AAE-UJdK8ZEij9fdp3TWjMh--q4TDWxLplU")      # CobraGroupBot token
HELPER_TOKEN = os.getenv("8509354978:AAH5_p72IvOY_66gv05nQw7qxAoTGKZrVsc")    # HelperFriend bot token
ADMIN_USER_ID = os.getenv("6623261004")      # numeric Telegram ID as string

if ADMIN_USER_ID is None:
    raise RuntimeError("ADMIN_USER_ID env var not set")
ADMIN_USER_ID = int(ADMIN_USER_ID)

if not COBRA_TOKEN or not HELPER_TOKEN:
    raise RuntimeError("COBRA_BOT_TOKEN or HELPER_BOT_TOKEN env vars not set")

ALLOWED_ADMINS = {ADMIN_USER_ID}

# =============================
# BOT INSTANCES + DISPATCHERS
# =============================

cobra_bot = Bot(COBRA_TOKEN)
cobra_dp = Dispatcher()

helper_bot = Bot(HELPER_TOKEN)
helper_dp = Dispatcher()


# =============================
# COMMON HELPERS
# =============================

def is_admin(user_id: int) -> bool:
    return user_id in ALLOWED_ADMINS


async def delete_later(bot: Bot, chat_id: int, message_id: int, delay: int = 300):
    """Delete a message after `delay` seconds."""
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception:
        pass


# =============================
# COBRA GROUP BOT (FILES BOT)
# =============================

# state per chat: chat_id -> {"files": [...], "waiting": bool}
PENDING_UPLOADS = {}


@cobra_dp.message(Command("start"))
async def cobra_start(message: types.Message):
    """
    /start ya /start token handle karega.
    Agar token hai -> files bhejega.
    Warna simple welcome.
    """
    parts = message.text.split(maxsplit=1)
    if len(parts) == 2:
        # deep-link with token
        token = parts[1].strip()
        content = get_content_by_token(token)
        if not content:
            await message.answer("❌ Link expired or invalid.")
            return

        files = get_files_for_content(content["id"])

        disclaimer = await message.answer(
            "⚠️ Videos will auto delete in 5 minutes."
        )
        asyncio.create_task(
            delete_later(cobra_bot, disclaimer.chat.id, disclaimer.message_id)
        )

        for f in files:
            msg = await message.answer_video(f["file_id"])
            asyncio.create_task(
                delete_later(cobra_bot, msg.chat.id, msg.message_id)
            )
    else:
        await message.answer(
            "Welcome to CobraGroupBot!\nOnly admin can upload files."
        )


@cobra_dp.message(Command("addfiles"))
async def cobra_addfiles(message: types.Message):
    """Admin ke liye: upload/forward files start."""
    if not is_admin(message.from_user.id):
        await message.answer("❌ You are not authorized.")
        return

    chat_id = message.chat.id
    PENDING_UPLOADS[chat_id] = {"files": [], "waiting": False}
    await message.answer("Send all video files (upload or forward), then type /end")


@cobra_dp.message(Command("end"))
async def cobra_end(message: types.Message):
    """Admin ke liye: files khatam, ab title maango."""
    if not is_admin(message.from_user.id):
        return

    chat_id = message.chat.id
    state = PENDING_UPLOADS.get(chat_id)
    if not state or not state["files"]:
        await message.answer("❌ No files received!")
        return

    state["waiting"] = True
    await message.answer("✔️ Now send video title / search keyword")


@cobra_dp.message()
async def cobra_collect_or_title(message: types.Message):
    """
    /addfiles ke baad:
    - pehle videos collect karega (waiting=False)
    - /end ke baad pehla text -> title save karega (waiting=True)
    """
    chat_id = message.chat.id
    state = PENDING_UPLOADS.get(chat_id)
    if not state:
        return  # koi active session nahi

    # 1) Files collect mode
    if not state["waiting"]:
        file_id = None

        if message.video:
            file_id = message.video.file_id
        elif message.document:
            mime = message.document.mime_type or ""
            if mime.startswith("video"):
                file_id = message.document.file_id

        if not file_id:
            # not a video / video-document, ignore
            return

        state["files"].append(file_id)
        print("Saved file_id:", file_id)
        await message.answer("Video received.")
        return

    # 2) Title receive mode
    if state["waiting"] and message.text:
        title = message.text.strip()
        if not title:
            await message.answer("Please send a valid title.")
            return

        keyword = title.lower()
        import secrets

        token = secrets.token_urlsafe(8)

        content_id = save_content(title, keyword, token)
        for fid in state["files"]:
            save_file(content_id, fid)

        link = f"https://t.me/{(await cobra_bot.get_me()).username}?start={token}"

        await message.answer(
            f"✔️ Saved successfully.\n\nTitle: {title}\nLink: {link}"
        )

        PENDING_UPLOADS.pop(chat_id, None)


# =============================
# HELPER FRIEND BOT (SEARCH BOT)
# =============================

# optional: agar sirf ek group me chalana ho to yaha group ID daal sakte ho
ALLOWED_CHATS = None  # e.g. { -1001234567890 }


@helper_dp.message(Command("start"))
async def helper_start(message: types.Message):
    await message.answer("Helper Friend ready! Type movie / clip name in group.")


@helper_dp.message()
async def helper_on_message(message: types.Message):
    # sirf groups me kaam kare
    if message.chat.type not in ("group", "supergroup"):
        return

    # agar allowed chats set hai to sirf unhi me
    if ALLOWED_CHATS is not None and message.chat.id not in ALLOWED_CHATS:
        return

    # commands ignore karo
    if message.text and message.text.startswith("/"):
        return

    if not message.text:
        return

    query = message.text.strip()
    if len(query) < 2:
        return

    results = search_contents(query)
    if not results:
        return

    # cobra bot ka username lazily fetch kar lete hain
    cobra_me = await cobra_bot.get_me()
    cobra_username = cobra_me.username

    for r in results:
        title = r["title"]
        token = r["token"]
        link = f"https://t.me/{cobra_username}?start={token}"

        text = (
            f"Title: {title}\n"
            f"👉👉 <a href=\"{link}\">Download now</a> 👈👈"
        )

        await message.reply(text, parse_mode="HTML")


# =============================
# MAIN: run both bots together
# =============================

async def main():
    print("Initializing database...")
    init_db()
    print("Starting CobraGroupBot and HelperFriend...")

    await asyncio.gather(
        cobra_dp.start_polling(cobra_bot),
        helper_dp.start_polling(helper_bot),
    )


if __name__ == "__main__":
    asyncio.run(main())
