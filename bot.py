import os
import random
import string
import threading
import asyncio
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TOKEN = os.environ["BOT_TOKEN"]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

LETTERS = string.ascii_lowercase
DIGITS = string.digits

# ---------------------------------------------------------------
# كل دالة ترجع: True = متاح ، False = غير متاح ، None = ما قدرت أتحقق
# ---------------------------------------------------------------


async def check_tiktok(client, name):
    try:
        r = await client.get(f"https://www.tiktok.com/@{name}", headers=HEADERS)
    except Exception:
        return None
    if r.status_code == 404:
        return True
    if r.status_code == 200:
        t = r.text
        if '"statusCode":10221' in t or '"statusCode":10202' in t:
            return True
        if '"uniqueId"' in t or '"statusCode":0' in t:
            return False
    return None


async def check_instagram(client, name):
    try:
        r = await client.get(
            f"https://www.instagram.com/{name}/", headers=HEADERS, follow_redirects=False
        )
    except Exception:
        return None
    if r.status_code == 404:
        return True
    if r.status_code == 200 and f"@{name}" in r.text.lower():
        return False
    return None


async def check_snapchat(client, name):
    try:
        r = await client.get(f"https://www.snapchat.com/add/{name}", headers=HEADERS)
    except Exception:
        return None
    if r.status_code == 404:
        return True
    if r.status_code == 200 and name in r.text.lower():
        return False
    return None


async def check_discord(client, name):
    try:
        r = await client.post(
            "https://discord.com/api/v9/unique-username/username-attempt-unauthed",
            json={"username": name},
            headers={"User-Agent": HEADERS["User-Agent"]},
        )
    except Exception:
        return None
    if r.status_code == 200:
        try:
            return not r.json().get("taken", True)
        except Exception:
            return None
    return None


async def check_psn(client, name):
    try:
        r = await client.post(
            "https://accounts.api.playstation.com/api/v1/accounts/onlineIds",
            json={"onlineId": name, "reserveIfAvailable": False},
            headers={"User-Agent": HEADERS["User-Agent"]},
        )
    except Exception:
        return None
    if r.status_code in (200, 201, 204):
        return True
    if r.status_code == 400:
        return False
    return None


SERVICES = {
    "TikTok": check_tiktok,
    "Instagram": check_instagram,
    "Snapchat": check_snapchat,
    "Discord": check_discord,
    "PlayStation": check_psn,
}


def random_name():
    """يوزر من 3 أو 4 خانات يناسب كل البرامج: يبدأ بحرف وينتهي بحرف أو رقم"""
    length = random.choice([3, 4])
    first = random.choice(LETTERS)
    last = random.choice(LETTERS + DIGITS)
    middle = "".join(random.choice(LETTERS + DIGITS + "_") for _ in range(length - 2))
    return first + middle + last


tasks = {}


async def search_loop(bot, chat_id):
    checked = set()
    # حالة كل برنامج: عدد الفشل المتتالي ووقت الإيقاف المؤقت
    state = {s: {"fails": 0, "pause_until": 0.0} for s in SERVICES}

    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        while True:
            name = random_name()
            if name in checked:
                continue
            checked.add(name)

            now = time.time()
            active = [s for s in SERVICES if state[s]["pause_until"] <= now]
            if not active:
                await asyncio.sleep(5)
                continue

            results = await asyncio.gather(
                *(SERVICES[s](client, name) for s in active)
            )

            available = []
            for s, res in zip(active, results):
                st = state[s]
                if res is None:
                    st["fails"] += 1
                    if st["fails"] >= 10:
                        st["pause_until"] = time.time() + 120
                        st["fails"] = 0
                else:
                    st["fails"] = 0
                    if res is True:
                        available.append(s)

            if available:
                await bot.send_message(chat_id, f"✅ {name} — " + " ، ".join(available))

            await asyncio.sleep(2)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in tasks and not tasks[chat_id].done():
        await update.message.reply_text("البحث شغال أصلاً 🔍\nلإيقافه أرسل /stop")
        return
    tasks[chat_id] = asyncio.create_task(search_loop(context.bot, chat_id))
    await update.message.reply_text(
        "بديت البحث عن يوزرات من 3 و4 خانات 🔍\n"
        "البرامج: TikTok, Instagram, Snapchat, Discord, PlayStation\n"
        "ما راح أرسل لك إلا المتاح.\n"
        "لإيقافه أرسل /stop"
    )


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    t = tasks.get(chat_id)
    if t and not t.done():
        t.cancel()
        await update.message.reply_text("وقفت البحث ⏹")
    else:
        await update.message.reply_text("ما في بحث شغال.")


class Ping(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass


def run_ping():
    port = int(os.environ.get("PORT", 10000))
    HTTPServer(("0.0.0.0", port), Ping).serve_forever()


async def main():
    threading.Thread(target=run_ping, daemon=True).start()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop))
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
