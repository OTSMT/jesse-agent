import os
import random
import asyncio
import datetime
import traceback
import json
import time

from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters
from notion_client import Client

print("JESSE BOT STARTED")

# ==================================================
# ENV
# ==================================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
NOTION_DB_ID = os.getenv("NOTION_DB_ID")

notion = Client(auth=NOTION_API_KEY)

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
        "chat_id": None,

        # EVOLUTION SYSTEM
        "discipline_score": 50,
        "consistency_score": 100,
        "last_decay": str(datetime.date.today()),
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
# TASK SYSTEM
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
# EVOLUTION ENGINE
# ==================================================
def evolve():
    today = datetime.date.today().isoformat()

    if MEMORY.get("last_decay") != today:
        MEMORY["discipline_score"] -= 1
        MEMORY["discipline_score"] = max(0, MEMORY["discipline_score"])
        MEMORY["last_decay"] = today

    added = MEMORY.get("tasks_added", 0)
    done = MEMORY.get("tasks_done", 0)

    ratio = done / max(1, added)
    MEMORY["consistency_score"] = int(ratio * 100)

    if ratio > 0.8:
        MEMORY["discipline_score"] += 2
    elif ratio < 0.4:
        MEMORY["discipline_score"] -= 2

    MEMORY["discipline_score"] = max(0, min(100, MEMORY["discipline_score"]))

def personality_state():
    evolve()

    s = MEMORY["discipline_score"]

    if s >= 80:
        return "machine"
    if s >= 60:
        return "disciplined"
    if s >= 40:
        return "neutral"
    if s >= 20:
        return "lazy"
    return "chaos"

# ==================================================
# JESSE ENGINE
# ==================================================
def mood(task_count):
    state = personality_state()

    if task_count == 0:
        return "empty"
    if state in ["machine", "disciplined"]:
        return "focused"
    if state == "neutral":
        return "calm"
    return "overloaded"

def jesse(event, task_count):
    update_streak()

    state = personality_state()

    moods = {
        "calm": ["Yo. ", "Alright. "],
        "focused": ["Locked in. ", "Yo. "],
        "overloaded": ["Yo... ", "Bro... "],
        "empty": ["... ", "Yo. "]
    }

    lines = {
        "task_added": ["Added it.", "Got it.", "Locked in."],
        "task_done": ["Done.", "Nice.", "Off the board."],
        "not_found": ["Not found.", "Nah.", "You sure?"],
        "list": ["Board:", "Here’s everything:"],
        "empty": ["Nothing left.", "Clean board."],
        "focus": ["Do this → ", "Focus → "]
    }

    state_lines = {
        "machine": "Elite execution.",
        "disciplined": "Good consistency.",
        "neutral": "",
        "lazy": "You slipping.",
        "chaos": "Fix this."
    }

    base = random.choice(moods[mood(task_count)])
    text = random.choice(lines.get(event, ["Yo."]))
    suffix = state_lines[state]

    return base + text + " " + suffix

# ==================================================
# CORE LOGIC
# ==================================================
def reply(text):
    task_count = len(pending_tasks())
    MEMORY["conversations"] += 1

    if text == "list":
        tasks = pending_tasks()
        if not tasks:
            return jesse("empty", task_count), "empty"

        body = "\n- ".join(extract_title(t) for t in tasks)
        return jesse("list", task_count) + "\n- " + body, "list"

    if text == "focus":
        tasks = pending_tasks()
        if not tasks:
            return jesse("empty", task_count), "empty"

        return jesse("focus", task_count) + extract_title(tasks[0]), "focus"

    if text.startswith("add"):
        save_task(text.replace("add", "", 1).strip())
        MEMORY["tasks_added"] += 1
        return jesse("task_added", task_count), "add"

    if text.startswith("done"):
        ok = mark_done(text.replace("done", "", 1).strip())
        if ok:
            MEMORY["tasks_done"] += 1
            return jesse("task_done", task_count), "done"
        return jesse("not_found", task_count), "default"

    return jesse("list", task_count), "default"

# ==================================================
# HANDLER
# ==================================================
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = update.message.text.lower().strip()

        response, _ = reply(text)

        save_memory(MEMORY)

        await update.message.reply_text(response)

    except Exception as e:
        print("ERROR:", e)
        traceback.print_exc()

# ==================================================
# RUN
# ==================================================
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    app.run_polling()

if __name__ == "__main__":
    main()
