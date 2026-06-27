import os
import random
import time
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
# GIFS (by intent)
# -------------------------
GIFS = {
    "add": [
        "CgACAgQAAxkBAANxaj0LFl0u4HHc0CpZWroUYFZ8loAAAtUCAAJVlQxTBkmzB2EPQCo8BA"
    ],
    "done": [
        "CgACAgQAAxkBAANyaj0LJVuPaT_cfd4RvqIivMF4vdMAAv4CAAKzsAxTGIFPam3qjak8BA"
    ],
    "focus": [
        "CgACAgQAAxkBAANzaj0LQ3LnyEwYQ_aw8-CtZsA07l4AAhwHAAJ2b0VQAAFnz-zlNdQgPAQ"
    ],
    "list": [],
    "empty": [],
    "overloaded": []
}

# -------------------------
# NOTION TASK HELPERS
# -------------------------
def get_tasks():
    try:
        return notion.databases.query(database_id=NOTION_DB_ID).get("results", [])
    except Exception as e:
        print("Notion error:", e)
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
# JESSE MEMORY (NOTION-BASED)
# -------------------------
MEMORY_PAGE_NAME = "JESSE_MEMORY"

def get_memory_page():
    try:
        pages = notion.databases.query(database_id=NOTION_DB_ID).get("results", [])
        for p in pages:
            title = extract_title(p)
            if title.strip().upper() == MEMORY_PAGE_NAME:
                return p
    except Exception as e:
        print("Memory fetch error:", e)
    return None

def load_memory():
    page = get_memory_page()

    default = {
        "tasks_added": 0,
        "tasks_done": 0,
        "streak": 0,
        "last_day": None,
        "conversations": 0,
        "milestones": []
    }

    if not page:
        return default

    try:
        props = page.get("properties", {})
        data_prop = props.get("Data", {})
        rich = data_prop.get("rich_text", [])
        if rich:
            return {**default, **eval(rich[0]["plain_text"])}
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
    except Exception as e:
        print("Memory save error:", e)

MEMORY = load_memory()

# -------------------------
# STREAKS
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
# PERSONALITY ENGINE
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

    moods = {
        "calm": ["Yo. ", "Alright. ", "Aight. "],
        "focused": ["Lock in. ", "Yo. ", "Alright listen. "],
        "overloaded": ["Yo... ", "Bro... ", "This is a lot. "],
        "empty": ["... ", "Yo. ", "Damn. "]
    }

    lines = {
        "task_added": [
            "Added. It's on the board.",
            "Boom. Another mission.",
            "Aight. Got it.",
            "Hell yeah. We'll get to it."
        ],
        "task_done": [
            "Hell yeah.",
            "That's off the board.",
            "Boom. Done.",
            "Nice. One less problem."
        ],
        "not_found": [
            "Yo... I don't see that.",
            "Nah man, not here.",
            "You sure?"
        ],
        "list": [
            "Here's what's left:",
            "Alright, here's the board:",
            "Current missions:"
        ],
        "empty": [
            "Dude... nothing left.",
            "Board's clean.",
            "We actually finished everything."
        ],
        "focus": [
            "Do this → ",
            "Focus up → ",
            "Only this matters → "
        ]
    }

    m = mood(task_count)

    base = random.choice(moods[m])
    text = random.choice(lines.get(event, ["Yo."]))

    suffix_pool = ["", " yo.", " bitch.", " let's go.", " keep moving."]

    response = base + text + random.choice(suffix_pool)

    # rare Easter egg
    if random.random() < 0.03:
        response += "\n\nYeah. Science."

    return response

# -------------------------
# BOT LOGIC
# -------------------------
def reply(text):
    task_count = len(pending_tasks())

    MEMORY["conversations"] += 1

    if text == "list":
        tasks = pending_tasks()
        if not tasks:
            return jesse("empty", task_count)

        body = "\n- ".join(extract_title(t) for t in tasks)
        return jesse("list", task_count) + "\n- " + body

    if text == "focus":
        t = pending_tasks()
        if not t:
            return jesse("empty", task_count)
        return jesse("focus", task_count) + extract_title(t[0])

    if text.startswith("add"):
        task = text.replace("add", "", 1).strip()
        save_task(task)
        MEMORY["tasks_added"] += 1
        return jesse("task_added", task_count)

    if text.startswith("done"):
        task = text.replace("done", "", 1).strip()
        ok = mark_done(task)
        if ok:
            MEMORY["tasks_done"] += 1
        return jesse("task_done" if ok else "not_found", task_count)

    return jesse("task_added", task_count)

# -------------------------
# TELEGRAM
# -------------------------
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = update.message.text.lower().strip()

        response = reply(text)

        save_memory(MEMORY)

        await update.message.reply_text(response)

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
