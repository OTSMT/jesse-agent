import os
import random
import traceback
import requests

from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters

# -------------------------
# ENV
# -------------------------
print("BOT STARTED")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
NOTION_DB_ID = os.getenv("NOTION_DB_ID")

if not TELEGRAM_TOKEN or not NOTION_API_KEY or not NOTION_DB_ID:
    raise ValueError("Missing env vars")

# -------------------------
# NOTION HEADERS (RAW API)
# -------------------------
NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

# -------------------------
# GIFS
# -------------------------
JESSE_GIFS = {
    "add": "CgACAgQAAxkBAANxaj0LFl0u4HHc0CpZWroUYFZ8loAAAtUCAAJVlQxTBkmzB2EPQCo8BA",
    "done": "CgACAgQAAxkBAANyaj0LJVuPaT_cfd4RvqIivMF4vdMAAv4CAAKzsAxTGIFPam3qjak8BA",
    "focus": "CgACAgQAAxkBAANzaj0LQ3LnyEwYQ_aw8-CtZsA07l4AAhwHAAJ2b0VQAAFnz-zlNdQgPAQ",
}

DEFAULT_GIFS = [
    "CgACAgQAAxkBAANwaj0LDR9fIlU9WkEigLOHE5sV2wMAAiQDAAIqpyxTGZ0lrfl2IpQ8BA",
    "CgACAgQAAxkBAANuaj0K_bkzP8ZcOpEHDLI1WXXQtSYAAlgIAAIVdXxRISrlCSjFWs88BA",
]

def jesse(text):
    return random.choice(["Yo. ", "Alright. ", "Listen. ", "Bruh, "]) + text + " yo."

# -------------------------
# NOTION HELPERS (RAW API)
# -------------------------
def notion_query():
    url = f"https://api.notion.com/v1/databases/{NOTION_DB_ID}/query"
    return requests.post(url, headers=NOTION_HEADERS).json()


def notion_create(task):
    url = "https://api.notion.com/v1/pages"

    payload = {
        "parent": {"database_id": NOTION_DB_ID},
        "properties": {
            "Task Type": {
                "title": [{"text": {"content": task}}]
            },
            "Status Type": {
                "select": {"name": "Pending"}
            }
        }
    }

    return requests.post(url, headers=NOTION_HEADERS, json=payload).json()


def notion_update(page_id):
    url = f"https://api.notion.com/v1/pages/{page_id}"

    payload = {
        "properties": {
            "Status Type": {
                "select": {"name": "Done"}
            }
        }
    }

    return requests.patch(url, headers=NOTION_HEADERS, json=payload).json()

# -------------------------
# PARSE NOTION
# -------------------------
def extract_title(props):
    for _, v in props.items():
        if v.get("type") == "title":
            t = v.get("title", [])
            if t:
                return t[0].get("plain_text", "UNKNOWN TASK")
    return "UNKNOWN TASK"


def extract_status(props):
    for _, v in props.items():
        if v.get("type") == "select":
            s = v.get("select")
            if s and s.get("name"):
                return s["name"].lower().strip()
    return "pending"

# -------------------------
# GET TASKS
# -------------------------
def get_tasks():
    try:
        data = notion_query()

        tasks = []

        for r in data.get("results", []):
            props = r.get("properties", {})

            tasks.append({
                "title": extract_title(props),
                "status": extract_status(props)
            })

        return tasks

    except Exception as e:
        print("FETCH ERROR", e)
        traceback.print_exc()
        return []

# -------------------------
# FILTER
# -------------------------
def pending_tasks():
    return [t for t in get_tasks() if t["status"] != "done"]

def top_task():
    tasks = pending_tasks()
    return tasks[0]["title"] if tasks else None

# -------------------------
# ACTIONS
# -------------------------
def save_task(task):
    try:
        res = notion_create(task)
        print("CREATE RESPONSE:", res)
        return True
    except Exception as e:
        print("CREATE ERROR", e)
        return False


def mark_done(task_name):
    try:
        data = notion_query()

        for r in data.get("results", []):
            props = r.get("properties", {})
            title = extract_title(props)

            if task_name.lower() in title.lower():
                page_id = r["id"]
                notion_update(page_id)
                return True

        return False

    except Exception as e:
        print("DONE ERROR", e)
        return False

# -------------------------
# GIF
# -------------------------
async def send_gif(update: Update, key: str):
    try:
        if not update.message:
            return

        file_id = JESSE_GIFS.get(key) or random.choice(DEFAULT_GIFS)
        await update.message.reply_animation(animation=file_id)

    except Exception:
        traceback.print_exc()

# -------------------------
# LOGIC
# -------------------------
def reply_logic(text):
    text = text.lower().strip()

    if text == "list":
        tasks = pending_tasks()
        if not tasks:
            return jesse("No tasks found.")
        return jesse("Backlog:\n- " + "\n- ".join(t["title"] for t in tasks))

    if text == "focus":
        task = top_task()
        return jesse(f"Do this → {task}") if task else jesse("No tasks.")

    if text.startswith("add "):
        ok = save_task(text[4:].strip())
        return jesse("Task added.") if ok else jesse("Couldn't save task.")

    if text.startswith("done "):
        ok = mark_done(text[5:].strip())
        return jesse("Task completed.") if ok else jesse("Couldn't find task.")

    return jesse("Noted.")

# -------------------------
# HANDLER
# -------------------------
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        msg = update.message
        if not msg or not msg.text:
            return

        text = msg.text.strip()

        gif_key = None
        if text.startswith("add "):
            gif_key = "add"
        elif text.startswith("done "):
            gif_key = "done"
        elif text == "focus":
            gif_key = "focus"

        reply = reply_logic(text)

        await send_gif(update, gif_key)
        await msg.reply_text(reply)

    except Exception:
        traceback.print_exc()

# -------------------------
# MAIN
# -------------------------
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    app.run_polling()

if __name__ == "__main__":
    main()
