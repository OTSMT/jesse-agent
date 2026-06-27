import os
import random
import asyncio
import datetime
import traceback
import json
import shutil
import time

from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters
from notion_client import Client

print("JESSE BOT STARTED")

# ==================================================
# CONFIG
# ==================================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
NOTION_DB_ID = os.getenv("NOTION_DB_ID")

notion = Client(auth=NOTION_API_KEY)

DEBUG = True

def debug(*args):
    if DEBUG:
        print("[DEBUG]", *args)

# ==================================================
# SAFETY BACKUP
# ==================================================
def auto_backup():
    try:
        if not os.path.exists("backups"):
            os.makedirs("backups")

        timestamp = time.strftime("%Y%m%d-%H%M%S")
        shutil.copy("bot.py", f"backups/bot_{timestamp}.py")

        backups = sorted(os.listdir("backups"))
        if len(backups) > 10:
            os.remove(os.path.join("backups", backups[0]))

    except Exception as e:
        print("Backup failed:", e)

# ==================================================
# MEMORY (NOTION)
# ==================================================
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
            return {**default, **json.loads(data[0]["plain_text"])}
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
                        {"text": {"content": json.dumps(mem)}}
                    ]
                }
            },
        )
    except:
        pass

MEMORY = load_memory()

# ==================================================
# TASK SYSTEM (NOTION)
# ==================================================
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
                if sel and sel.get("name"):
                    return sel["name"].strip().lower()
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

# ==================================================
# STREAK
# ==================================================
def update_streak():
    today = datetime.date.today().isoformat()

    if MEMORY["last_day"] != today:
        yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()

        if MEMORY["last_day"] == yesterday:
            MEMORY["streak"] += 1
        else:
            MEMORY["streak"] = 1

        MEMORY["last_day"] = today

# ==================================================
# JESSE ENGINE (PERSONALITY)
# ==================================================
def mood(task_count):
    if task_count == 0:
        return "empty"
    if task_count <= 2:
        return "calm"
    if task_count <= 5:
        return "focused"
    return "overloaded"

def jesse(event, task_count):
    update_streak()

    moods = {
        "calm": ["Yo. ", "Alright. ", "Aight. "],
        "focused": ["Lock in. ", "Yo. ", "Listen. "],
        "overloaded": ["Yo... ", "Bro... ", "This is a lot. "],
        "empty": ["... ", "Yo. ", "Damn. "]
    }

    lines = {
        "task_added": ["Added it.", "Mission added.", "Got it.", "Hell yeah."],
        "task_done": ["Hell yeah.", "Done.", "Off the board.", "Nice."],
        "not_found": ["Yo... not here.", "Nah.", "You sure?"],
        "list": ["Here's the board:", "Current missions:", "Alright:"],
        "empty": ["Nothing left.", "Board's clean.", "We’re done."],
        "focus": ["Do this → ", "Focus → ", "Only this → "]
    }

    m = mood(task_count)

    base = random.choice(moods[m])
    text = random.choice(lines.get(event, ["Yo."]))

    suffixes = ["", " yo.", " let's go.", " keep moving."]
    return base + text + random.choice(suffixes)

# ==================================================
# COMMAND SYSTEM
# ==================================================
COMMANDS = {}

def command(name):
    def wrapper(func):
        COMMANDS[name] = func
        return func
    return wrapper

@command("list")
def cmd_list(text):
    tasks = pending_tasks()
    if not tasks:
        return jesse("empty", 0), "empty"

    body = "\n- ".join(extract_title(t) for t in tasks)
    return jesse("list", len(tasks)) + "\n- " + body, "list"

@command("add")
def cmd_add(text):
    task = text.replace("add", "", 1).strip()
    save_task(task)
    MEMORY["tasks_added"] += 1
    return jesse("task_added", len(pending_tasks())), "add"

@command("done")
def cmd_done(text):
    task = text.replace("done", "", 1).strip()
    ok = mark_done(task)
    if ok:
        MEMORY["tasks_done"] += 1
        return jesse("task_done", len(pending_tasks())), "done"
    return jesse("not_found", len(pending_tasks())), "default"

@command("focus")
def cmd_focus(text):
    tasks = pending_tasks()
    if not tasks:
        return jesse("empty", 0), "empty"

    top = tasks[0]
    return jesse("focus", len(tasks)) + extract_title(top), "focus"

def reply(text):
    MEMORY["conversations"] += 1

    for key, func in COMMANDS.items():
        if text.startswith(key):
            return func(text)

    return cmd_list(text)

# ==================================================
# TELEGRAM HANDLER
# ==================================================
def update_chat_id(update: Update):
    MEMORY["chat_id"] = update.effective_chat.id

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        update_chat_id(update)
        update_streak()

        text = update.message.text.lower().strip()

        debug("INPUT:", text)

        response, event = reply(text)

        save_memory(MEMORY)

        await update.message.reply_text(response)

    except Exception as e:
        debug("ERROR:", e)
        traceback.print_exc()

# ==================================================
# DAILY RECAP
# ==================================================
async def send_daily_recap(bot):
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

        except Exception as e:
            debug("RECAP ERROR:", e)

        await asyncio.sleep(3600)

# ==================================================
# MAIN
# ==================================================
def main():
    auto_backup()

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

    asyncio.get_event_loop().create_task(send_daily_recap(app.bot))

    app.run_polling()

if __name__ == "__main__":
    main()
