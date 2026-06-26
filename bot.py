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
# GIFS (KEEP YOUR WORKING IDS)
# -------------------------
JESSE_GIFS = {
    "add": "CgACAgQAAxkBAANxaj0LFl0u4HHc0CpZWroUYFZ8loAAAtUCAAJVlQxTBkmzB2EPQCo8BA",
    "done": "CgACAgQAAxkBAANyaj0LJVuPaT_cfd4RvqIivMF4vdMAAv4CAAKzsAxTGIFPam3qjak8BA",
    "focus": "CgACAgQAAxkBAANzaj0LQ3LnyEwYQ_aw8-CtZsA07l4AAhwHAAJ2b0VQAAFnz-zlNdQgPAQ",
}

# -------------------------
# MEMORY (SIMPLE + SAFE)
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
            "last_day": None
        }

MEMORY = load_memory()

def save_memory():
    with open(MEM_FILE, "w") as f:
        json.dump(MEMORY, f)

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
# JESSE (SIMPLE STABLE VERSION)
# -------------------------
def jesse(text, task_count):
    moods = ["Yo. ", "Alright. ", "Listen. ", "Yo yo. "]
    suffix = ["", " stay sharp.", " you got this.", " let's go."]
    return random.choice(moods) + text + random.choice(suffix)

# -------------------------
# REPLY LOGIC (UNCHANGED CORE)
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
        t = pending_tasks()
        return jesse(f"Do this → {extract_title(t[0])}" if t else "No tasks.", task_count)

    if text.startswith("add"):
        save_task(text.replace("add", "", 1).strip())
        MEMORY["tasks_added"] += 1
        return jesse("Task added.", task_count)

    if text.startswith("done"):
        ok = mark_done(text.replace("done", "", 1).strip())
        if ok:
            MEMORY["tasks_done"] += 1
        return jesse("Done." if ok else "Not found.", task_count)

    return jesse("Noted.", task_count)

# -------------------------
# GIF SENDER (SAFE)
# -------------------------
async def send_gif(update: Update, key: str):
    try:
        gif = JESSE_GIFS.get(key)
        if gif:
            await update.get_bot().send_animation(
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
        text = update.message.text

        response = reply(text)

        save_memory()

        await update.message.reply_text(response)

        # simple fallback gif (no logic complexity)
        await send_gif(update, "focus")

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
