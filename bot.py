import os
import random
import asyncio
import datetime
import traceback

from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters
from notion_client import Client

print("JESSE BOT STARTED")

# -------------------------
# ENV
# -------------------------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
NOTION_DB_ID = os.getenv("NOTION_DB_ID")

notion = Client(auth=NOTION_API_KEY)

# -------------------------
# MEMORY (NO CHAT ID REQUIRED MANUALLY)
# -------------------------
MEMORY_PAGE_NAME = "JESSE_MEMORY"

def get_memory_page():
    try:
        pages = notion.databases.query(database_id=NOTION_DB_ID).get("results", [])
        for p in pages:
            props = p.get("properties", {})
            title = props.get("Task", {}).get("title", [])
            if title and title[0]["plain_text"].strip().upper() == MEMORY_PAGE_NAME:
                return p
    except:
        pass
    return None

def load_memory():
    page = get_memory_page()

    default = {
        "tasks_added": 0,
        "tasks_done": 0,
        "streak": 0,
        "last_day": None,
        "conversations": 0,
        "last_recap_date": None,
        "chat_id": None
    }

    if not page:
        return default

    try:
        props = page.get("properties", {})
        data = props.get("Data", {}).get("rich_text", [])
        if data:
            return {**default, **eval(data[0]["plain_text"])}
    except:
        pass

    return default

def save_memory(mem):
    page = get_memory_page()
    if not page:
        return

    try:
        notion.pages.update(
            page_id=page["id"],
            properties={
                "Data": {
                    "rich_text": [
                        {"text": {"content": str(mem)}}
                    ]
                }
            },
        )
    except:
        pass

MEMORY = load_memory()

# -------------------------
# GIFS
# -------------------------
GIFS = {
    "add": ["CgACAgQAAxkBAANxaj0LFl0u4HHc0CpZWroUYFZ8loAAAtUCAAJVlQxTBkmzB2EPQCo8BA"],
    "done": ["CgACAgQAAxkBAANyaj0LJVuPaT_cfd4RvqIivMF4vdMAAv4CAAKzsAxTGIFPam3qjak8BA"],
    "focus": ["CgACAgQAAxkBAANzaj0LQ3LnyEwYQ_aw8-CtZsA07l4AAhwHAAJ2b0VQAAFnz-zlNdQgPAQ"]
}

# -------------------------
# TASKS (UNCHANGED)
# -------------------------
def get_tasks():
    try:
        return notion.databases.query(database_id=NOTION_DB_ID).get("results", [])
    except:
        return []

def extract_title(page):
    try:
        props = page.get("properties", {})
        for v in props.values():
            if v.get("type") == "title":
                t = v.get("title", [])
                return t[0]["plain_text"] if t else "UNKNOWN"
    except:
        pass
    return "UNKNOWN"

def extract_status(page):
    try:
        props = page.get("properties", {})
        for v in props.values():
            if v.get("type") == "select":
                sel = v.get("select")
                if sel:
                    return sel["name"].lower()
        return "pending"
    except:
        return "pending"

def pending_tasks():
    return [t for t in get_tasks() if extract_status(t) != "done"]

def save_task(text):
    notion.pages.create(
        parent={"database_id": NOTION_DB_ID},
        properties={
            "Task": {"title": [{"text": {"content": text}}]},
            "Status": {"select": {"name": "Pending"}},
        },
    )

def mark_done(name):
    for t in get_tasks():
        if extract_title(t).strip().lower() == name.strip().lower():
            notion.pages.update(
                page_id=t["id"],
                properties={"Status": {"select": {"name": "Done"}}},
            )
            return True
    return False

# -------------------------
# STREAK
# -------------------------
def update_streak():
    today = datetime.date.today().isoformat()

    if MEMORY["last_day"] != today:
        yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()

        if MEMORY["last_day"] == yesterday:
            MEMORY["streak"] += 1
        else:
            MEMORY["streak"] = 1

        MEMORY["last_day"] = today

# -------------------------
# JESSE TEXT
# -------------------------
def jesse(text):
    return random.choice([
        "Yo. ",
        "Alright. ",
        "Aight. ",
        "Bro. "
    ]) + text + random.choice(["", " bitch.", " let's go.", " yo."])

# -------------------------
# CHAT ID AUTO DETECTION
# -------------------------
def update_chat_id(update: Update):
    global MEMORY

    chat_id = update.effective_chat.id

    if MEMORY.get("chat_id") is None:
        MEMORY["chat_id"] = chat_id
        save_memory(MEMORY)

# -------------------------
# CORE LOGIC
# -------------------------
def reply(text):
    task_count = len(pending_tasks())

    if text == "add":
        return jesse("Added task."), "add"

    if text == "done":
        return jesse("Marked done."), "done"

    if text == "list":
        return jesse("Listing tasks."), "list"

    return jesse("Noted."), "default"

# -------------------------
# GIF ENGINE
# -------------------------
async def send_gif(update: Update, event: str):
    try:
        gifs = GIFS.get(event, [])
        if not gifs:
            return

        await update.get_bot().send_animation(
            chat_id=update.effective_chat.id,
            animation=random.choice(gifs)
        )
    except:
        pass

# -------------------------
# DAILY RECAP (AUTO CHAT ID)
# -------------------------
async def send_daily_recap(bot):
    global MEMORY

    while True:
        try:
            today = datetime.date.today().isoformat()

            if MEMORY.get("chat_id") and MEMORY.get("last_recap_date") != today:

                msg = (
                    f"Yo.\n"
                    f"Streak: {MEMORY.get('streak', 0)}\n"
                    f"Pending: {len(pending_tasks())}"
                )

                await bot.send_message(
                    chat_id=MEMORY["chat_id"],
                    text=msg
                )

                MEMORY["last_recap_date"] = today
                save_memory(MEMORY)

        except:
            pass

        await asyncio.sleep(3600)

# -------------------------
# HANDLER
# -------------------------
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        update_chat_id(update)
        update_streak()

        text = update.message.text.lower().strip()

        response, event = reply(text)

        save_memory(MEMORY)

        await update.message.reply_text(response)
        await send_gif(update, event)

    except Exception as e:
        print("ERROR:", e)
        traceback.print_exc()

# -------------------------
# RUN
# -------------------------
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

    asyncio.get_event_loop().create_task(send_daily_recap(app.bot))

    app.run_polling()

if __name__ == "__main__":
    main()
