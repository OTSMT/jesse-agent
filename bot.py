import os
import random
import time
import json
import datetime
import traceback

from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters
from notion_client import Client

print("BOT STARTED")

# -------------------------
# ENV
# -------------------------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
NOTION_DB_ID = os.getenv("NOTION_DB_ID")

notion = Client(auth=NOTION_API_KEY)

# -------------------------
# GIFS
# -------------------------
JESSE_GIFS = {
    "add": "CgACAgQAAxkBAANxaj0LFl0u4HHc0CpZWroUYFZ8loAAAtUCAAJVlQxTBkmzB2EPQCo8BA",
    "done": "CgACAgQAAxkBAANyaj0LJVuPaT_cfd4RvqIivMF4vdMAAv4CAAKzsAxTGIFPam3qjak8BA",
    "focus": "CgACAgQAAxkBAANzaj0LQ3LnyEwYQ_aw8-CtZsA07l4AAhwHAAJ2b0VQAAFnz-zlNdQgPAQ",
}

# -------------------------
# MEMORY (SINGLE USER)
# -------------------------
MEM_FILE = "jesse_memory.json"

def load_memory():
    try:
        with open(MEM_FILE, "r") as f:
            return json.load(f)
    except:
        return {
            "tasks_added": 0,
            "tasks_done": 0,
            "last_seen": time.time(),
            "streak": 0,
            "last_day": None,
            "weekly_added": 0,
            "weekly_done": 0,
            "week_start": time.time()
        }

MEMORY = load_memory()

def save_memory():
    with open(MEM_FILE, "w") as f:
        json.dump(MEMORY, f)

# -------------------------
# STREAK + WEEK
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

def update_week():
    if time.time() - MEMORY["week_start"] > 7 * 24 * 3600:
        MEMORY["weekly_added"] = 0
        MEMORY["weekly_done"] = 0
        MEMORY["week_start"] = time.time()

def update_activity():
    now = time.time()

    if now - MEMORY["last_seen"] > 6 * 3600:
        MEMORY["streak"] = max(0, MEMORY["streak"] - 1)

    MEMORY["last_seen"] = now

    update_streak()
    update_week()

# -------------------------
# NOTION
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
# PERSONALITY
# -------------------------
def get_personality():
    ratio = MEMORY["tasks_done"] / max(1, MEMORY["tasks_added"])

    if MEMORY["streak"] >= 5:
        return "disciplined"

    if ratio < 0.3:
        return "chaotic"

    if MEMORY["tasks_added"] > 10:
        return "experienced"

    return "balanced"

def mood(task_count):
    if task_count == 0:
        return "calm"
    if task_count <= 2:
        return "focused"
    if task_count <= 5:
        return "busy"
    return "overloaded"

def jesse(text, task_count):
    p = get_personality()
    m = mood(task_count)

    prefix = {
        "balanced": ["Yo. ", "Alright. "],
        "experienced": ["Back again. ", "Same thing huh. "],
        "disciplined": ["I respect it. ", "Locked in. "],
        "chaotic": ["Bro… ", "This is wild. "],
    }.get(p, ["Yo. "])

    mood_prefix = {
        "calm": ["Chill. ", "Alright. "],
        "focused": ["Lock in. ", "Listen. "],
        "busy": ["We moving. ", "Keep going. "],
        "overloaded": ["Yo this is a lot. ", "We cooked. "],
    }.get(m, ["Yo. "])

    suffix = {
        "calm": [" we good.", ""],
        "focused": [" stay sharp.", " you got this."],
        "busy": [" keep going.", " we in it."],
        "overloaded": [" we need cleanup.", " too much man."],
    }.get(m, [" yo."])

    return random.choice(prefix + mood_prefix) + text + random.choice(suffix)

# -------------------------
# REPLY
# -------------------------
def reply(text):
    task_count = len(pending_tasks())

    if text == "list":
        return jesse(
            "Tasks:\n- " + "\n- ".join(extract_title(t) for t in pending_tasks())
            if task_count else "No pending jobs.",
            task_count
        )

    if text == "focus":
        t = pending_tasks()
        return jesse(f"Do this → {extract_title(t[0])}" if t else "No tasks.", task_count)

    if text.startswith("add"):
        save_task(text.replace("add", "", 1).strip())
        MEMORY["tasks_added"] += 1
        MEMORY["weekly_added"] += 1
        return jesse("Task added.", task_count)

    if text.startswith("done"):
        ok = mark_done(text.replace("done", "", 1).strip())
        if ok:
            MEMORY["tasks_done"] += 1
            MEMORY["weekly_done"] += 1
        return jesse("Done." if ok else "Not found.", task_count)

    return jesse("Noted.", task_count)

# -------------------------
# GIF
# -------------------------
async def send_gif(update: Update):
    try:
        await update.get_bot().send_animation(
            chat_id=update.effective_chat.id,
            animation=random.choice(list(JESSE_GIFS.values()))
        )
    except:
        pass

# -------------------------
# HANDLER
# -------------------------
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        update_activity()

        text = update.message.text.lower().strip()

        response = reply(text)

        save_memory()

        await update.message.reply_text(response)
        await send_gif(update)

    except Exception as e:
        print("ERROR:", e)
        traceback.print_exc()

# -------------------------
# RUN
# -------------------------
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    app.run_polling()

if __name__ == "__main__":
    main()
