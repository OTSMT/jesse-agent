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
# MEMORY
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
        "chat_id": None,

        # SMART JESSE ADDITIONS
        "recent_actions": [],
        "fail_streak": 0,
        "success_streak": 0,
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
# TASKS
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
# SMART JESSE BEHAVIOR SYSTEM
# -------------------------
def track_action(action):
    MEMORY["recent_actions"].append(action)

    if len(MEMORY["recent_actions"]) > 5:
        MEMORY["recent_actions"].pop(0)

def analyze_behavior():
    recent = MEMORY.get("recent_actions", [])

    adds = recent.count("add")
    dones = recent.count("done")

    if adds >= 3 and dones == 0:
        return "overwhelming"

    if dones >= adds and adds > 0:
        return "productive"

    if adds == 0 and dones == 0:
        return "idle"

    return "normal"

# -------------------------
# JESSE RESPONSES
# -------------------------
JESSE_LINES = {
    "task_added": ["Added it.", "Got it.", "Locked in.", "Say less.", "Bet.", "On it."],
    "task_done": ["Yeah, bitch!", "Done.", "Nice.", "Off the board.", "Clean.", "We cookin'."],
    "not_found": ["Yo… not here.", "That’s not in the list.", "You sure?", "Nah, not found."],
    "list": ["Here’s the board:", "Current missions:", "Alright, here’s everything:"],
    "empty": ["Nothing left.", "Board’s clean.", "We’re done here."],
    "focus": ["Do this → ", "Focus → ", "Only this → "]
}

# -------------------------
# GIF SYSTEM
# -------------------------
GIFS = {
    "task_added": [
        "CgACAgQAAxkBAAIFpGo_i6l-7y4q7oZeumVRjAMha46MAAJMBgACCpJFUc5OZtXsmw9OPAQ"
    ],
    "task_done": [
        "CgACAgQAAxkBAANvaj0LBnguOITXUPIWodCIx7BUCGsAArYDAAKCb51QTuahwuylJAk8BA",
        "CgACAgQAAxkBAAIEeWo_F9QX-x12U1EejZaXVvwcHPtsAAJKAwACaoAEU0BH5rBCYtisPAQ"
    ],
    "focus": [
        "CgACAgQAAxkBAAIFpGo_i6l-7y4q7oZeumVRjAMha46MAAJMBgACCpJFUc5OZtXsmw9OPAQ",
        "CgACAgQAAxkBAANuaj0K_bkzP8ZcOpEHDLI1WXXQtSYAAlgIAAIVdXxRISrlCSjFWs88BA"
    ],
    "default": [
        "CgACAgQAAxkBAANwaj0LDR9fIlU9WkEigLOHE5sV2wMAAiQDAAIqpyxTGZ0lrfl2IpQ8BA"
    ]
}

def get_gif(event):
    pool = GIFS.get(event, GIFS["default"])
    return random.choice(pool) if pool else None

async def send_gif(update: Update, event: str):
    try:
        gif = get_gif(event)
        if not gif:
            return

        await update.get_bot().send_animation(
            chat_id=update.effective_chat.id,
            animation=gif
        )
    except:
        pass

# -------------------------
# SMART JESSE ENGINE
# -------------------------
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

    behavior = analyze_behavior()

    moods = {
        "calm": ["Yo. ", "Alright. ", "Aight. "],
        "focused": ["Lock in. ", "Yo. ", "Listen. "],
        "overloaded": ["Yo... ", "Bro... ", "This is a lot. "],
        "empty": ["... ", "Yo. ", "Damn. "]
    }

    behavior_lines = {
        "overwhelming": ["Yo slow down.", "You're stacking too much.", "Relax for a sec."],
        "productive": ["We moving clean.", "This is good.", "Locked in behavior."],
        "idle": ["You disappeared.", "We doing nothing?", "Hello?"],
        "normal": [""]
    }

    base = random.choice(moods[mood(task_count)])
    behavior_layer = random.choice(behavior_lines[behavior])
    event_line = random.choice(JESSE_LINES.get(event, ["Yo."]))
    suffix = random.choice(["", " yo.", " let's go.", " keep moving."])

    return base + behavior_layer + event_line + suffix

# -------------------------
# CORE LOGIC
# -------------------------
def reply(text):
    task_count = len(pending_tasks())
    MEMORY["conversations"] += 1

    if text == "list":
        tasks = pending_tasks()
        if not tasks:
            return "Nothing left.", "empty"

        body = "\n- ".join(extract_title(t) for t in tasks)
        return random.choice(JESSE_LINES["list"]) + "\n- " + body, "list"

    if text == "focus":
        tasks = pending_tasks()
        if not tasks:
            return "Nothing left.", "empty"

        return random.choice(JESSE_LINES["focus"]) + extract_title(tasks[0]), "focus"

    if text.startswith("add"):
        task = text.replace("add", "", 1).strip()
        save_task(task)
        MEMORY["tasks_added"] += 1

        track_action("add")

        return random.choice(JESSE_LINES["task_added"]), "task_added"

    if text.startswith("done"):
        task = text.replace("done", "", 1).strip()
        ok = mark_done(task)

        track_action("done")

        if ok:
            MEMORY["tasks_done"] += 1
            return random.choice(JESSE_LINES["task_done"]), "task_done"

        return random.choice(JESSE_LINES["not_found"]), "default"

    return "Noted.", "default"

# -------------------------
# HANDLER
# -------------------------
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
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
    app.run_polling()

if __name__ == "__main__":
    main()
