import os
import random
import time
import traceback
import json
import datetime

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

if not TELEGRAM_TOKEN or not NOTION_API_KEY or not NOTION_DB_ID:
    raise ValueError("Missing env vars")

notion = Client(auth=NOTION_API_KEY)

# -------------------------
# GIFS (UNCHANGED)
# -------------------------
JESSE_GIFS = {
    "add": "CgACAgQAAxkBAANxaj0LFl0u4HHc0CpZWroUYFZ8loAAAtUCAAJVlQxTBkmzB2EPQCo8BA",
    "done": "CgACAgQAAxkBAANyaj0LJVuPaT_cfd4RvqIivMF4vdMAAv4CAAKzsAxTGIFPam3qjak8BA",
    "focus": "CgACAgQAAxkBAANzaj0LQ3LnyEwYQ_aw8-CtZsA07l4AAhwHAAJ2b0VQAAFnz-zlNdQgPAQ",
}

# -------------------------
# MEMORY SYSTEM (LONG TERM ARC)
# -------------------------
MEMORY_FILE = "jesse_memory.json"

def load_memory():
    try:
        with open(MEMORY_FILE, "r") as f:
            return json.load(f)
    except:
        return {
            "tasks_added": 0,
            "tasks_done": 0,
            "last_seen": time.time(),
            "sessions": 0,
            "last_active_day": None,
            "streak": 0,
            "weekly_added": 0,
            "weekly_done": 0,
            "week_start": time.time()
        }

def save_memory():
    with open(MEMORY_FILE, "w") as f:
        json.dump(MEMORY, f)

MEMORY = load_memory()

# -------------------------
# STREAK + WEEK SYSTEM
# -------------------------
def update_streak():
    today = datetime.date.today().isoformat()

    if MEMORY["last_active_day"] != today:
        if MEMORY["last_active_day"] is None:
            MEMORY["streak"] = 1
        else:
            yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()

            if MEMORY["last_active_day"] == yesterday:
                MEMORY["streak"] += 1
            else:
                MEMORY["streak"] = 1

        MEMORY["last_active_day"] = today
        save_memory()

def update_weekly():
    now = time.time()
    if now - MEMORY["week_start"] > 7 * 24 * 3600:
        MEMORY["weekly_added"] = 0
        MEMORY["weekly_done"] = 0
        MEMORY["week_start"] = now
        save_memory()

def update_session():
    now = time.time()

    if now - MEMORY["last_seen"] > 6 * 3600:
        MEMORY["sessions"] += 1

    MEMORY["last_seen"] = now

    update_streak()
    save_memory()

# -------------------------
# STATE (SHORT TERM)
# -------------------------
STATE = {
    "energy": 60,
    "stress": 10,
}

def decay_state():
    STATE["energy"] = max(0, STATE["energy"] - 0.5)
    STATE["stress"] = max(0, STATE["stress"] - 0.3)

def update_state(action, task_count):
    if action == "add":
        STATE["energy"] += 3
        STATE["stress"] += 2
        MEMORY["tasks_added"] += 1
        MEMORY["weekly_added"] += 1

    elif action == "done":
        STATE["energy"] += 2
        STATE["stress"] -= 3
        MEMORY["tasks_done"] += 1
        MEMORY["weekly_done"] += 1

    if task_count > 5:
        STATE["stress"] += 2

    STATE["energy"] = max(0, min(100, STATE["energy"]))
    STATE["stress"] = max(0, min(100, STATE["stress"]))

    save_memory()

# -------------------------
# PERSONALITY ENGINE
# -------------------------
def get_personality():
    ratio = MEMORY["tasks_done"] / max(1, MEMORY["tasks_added"])

    if MEMORY["streak"] >= 5:
        return "disciplined_streak"

    if MEMORY["sessions"] >= 5 and ratio > 0.7:
        return "disciplined"

    if ratio < 0.3:
        return "chaotic"

    if MEMORY["sessions"] >= 3:
        return "experienced"

    if MEMORY["streak"] == 0:
        return "inactive"

    return "balanced"

# -------------------------
# MOOD ENGINE
# -------------------------
def get_mood(task_count):
    decay_state()

    if task_count == 0:
        return "calm"

    if STATE["stress"] > 70:
        return "overloaded"

    if STATE["energy"] > 75:
        return "hyped"

    if task_count <= 2:
        return "focused"

    if task_count <= 5:
        return "busy"

    return "neutral"

def mood_prefix(mood, personality):
    base = {
        "calm": ["Yo. ", "Alright. "],
        "focused": ["Yo. ", "Lock in. "],
        "busy": ["Yo. ", "We moving. "],
        "overloaded": ["Yo!! ", "Bro… "],
        "hyped": ["YO! ", "LET’S GOOO! "],
        "neutral": ["Yo. ", "Alright. "],
    }.get(mood, ["Yo. "])

    personality_add = {
        "disciplined": ["I respect the grind. ", "You’re locked in. "],
        "disciplined_streak": ["you’re on fire. ", "this streak is insane. "],
        "chaotic": ["Bro we struggling 😭 ", "This is wild… "],
        "experienced": ["Back again. ", "Same routine huh. "],
        "inactive": ["yo where you been. ", "we fell off huh. "],
        "balanced": ["Alright. ", ""],
    }.get(personality, [""])

    return base + personality_add

def mood_suffix(mood, personality):
    return {
        "calm": [" yo.", "", " we chill."],
        "focused": [" stay sharp.", " you got this."],
        "busy": [" keep going.", " we in it."],
        "overloaded": [" this is too much.", " we need cleanup."],
        "hyped": [" LET’S GOO.", " this is fire."],
        "neutral": [" yo.", ""],
    }.get(mood, [" yo."])

# -------------------------
# JESSE CORE
# -------------------------
def jesse(text, task_count=0):
    mood = get_mood(task_count)
    personality = get_personality()

    return (
        random.choice(mood_prefix(mood, personality))
        + text
        + random.choice(mood_suffix(mood, personality))
    )

# -------------------------
# NOTION
# -------------------------
def get_tasks():
    try:
        res = notion.databases.query(database_id=NOTION_DB_ID)
        return res.get("results", [])
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

def top_task():
    tasks = pending_tasks()
    return extract_title(tasks[0]) if tasks else None

def save_task(text):
    notion.pages.create(
        parent={"database_id": NOTION_DB_ID},
        properties={
            "Task": {"title": [{"text": {"content": text}}]},
            "Status": {"select": {"name": "Pending"}},
        },
    )

def mark_done(name):
    tasks = get_tasks()

    for t in tasks:
        title = extract_title(t)

        if title.strip().lower() == name.strip().lower():
            notion.pages.update(
                page_id=t["id"],
                properties={"Status": {"select": {"name": "Done"}}},
            )
            return True

    return False

# -------------------------
# REPLY
# -------------------------
def reply(text):
    text = text.lower().strip()
    task_count = len(pending_tasks())

    if text == "list":
        return jesse(
            "Tasks:\n- " + "\n- ".join(extract_title(t) for t in pending_tasks())
            if task_count else "No pending jobs.",
            task_count
        )

    if text == "focus":
        task = top_task()
        return jesse(f"Do this → {task}" if task else "No tasks.", task_count)

    if text.startswith("add"):
        save_task(text.replace("add", "", 1).strip())
        update_state("add", task_count + 1)
        return jesse("Task added.", task_count + 1)

    if text.startswith("done"):
        ok = mark_done(text.replace("done", "", 1).strip())
        update_state("done", task_count)
        return jesse("Done." if ok else "Not found.", task_count)

    return jesse("Noted.", task_count)

# -------------------------
# GIF
# -------------------------
async def send_gif(update: Update, key: str):
    try:
        bot = update.get_bot()
        gif = JESSE_GIFS.get(key)

        if gif:
            await bot.send_animation(
                chat_id=update.effective_chat.id,
                animation=gif
            )
    except:
        pass

# -------------------------
# HANDLER
# -------------------------
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        update_session()
        update_weekly()

        text = update.message.text
        if not text:
            return

        response = reply(text)

        await update.message.reply_text(response)
        await send_gif(update, "focus")

    except Exception as e:
        print("ERROR:", e)

# -------------------------
# RUN
# -------------------------
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    app.run_polling()

if __name__ == "__main__":
    main()
