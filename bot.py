import os
import random
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

if not TELEGRAM_TOKEN or not NOTION_API_KEY or not NOTION_DB_ID:
    raise ValueError("Missing env vars")

notion = Client(auth=NOTION_API_KEY)

# -------------------------
# JESSE STYLE
# -------------------------
def jesse(text):
    return random.choice(["Yo. ", "Alright. ", "Listen. ", "Bruh, "]) + text + " yo."

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
]

# -------------------------
# NOTION HELPERS (ROBUST)
# -------------------------
def get_tasks():
    try:
        res = notion.databases.query(database_id=NOTION_DB_ID)
        return res.get("results", [])
    except Exception:
        traceback.print_exc()
        return []

def extract_title(page):
    try:
        props = page.get("properties", {})
        for v in props.values():
            if v.get("type") == "title":
                t = v.get("title", [])
                return t[0]["plain_text"] if t else "UNKNOWN"
        return "UNKNOWN"
    except:
        return "UNKNOWN"

def extract_status(page):
    try:
        props = page.get("properties", {})
        for v in props.values():
            if v.get("type") == "select":
                sel = v.get("select")
                if sel:
                    return sel.get("name", "").lower()
        return ""
    except:
        return ""

def pending_tasks():
    tasks = get_tasks()
    return [t for t in tasks if extract_status(t) != "done"]

def top_task():
    tasks = pending_tasks()
    return extract_title(tasks[0]) if tasks else None

# -------------------------
# NOTION ACTIONS
# -------------------------
def save_task(text):
    try:
        notion.pages.create(
            parent={"database_id": NOTION_DB_ID},
            properties={
                "Task": {"title": [{"text": {"content": text}}]},
                "Status": {"select": {"name": "Pending"}},
            },
        )
    except Exception:
        traceback.print_exc()

def mark_done(task_name):
    try:
        tasks = get_tasks()

        for t in tasks:
            title = extract_title(t)

            if title.lower().strip() == task_name.lower().strip():
                notion.pages.update(
                    page_id=t["id"],
                    properties={
                        "Status": {"select": {"name": "Done"}}
                    },
                )
                return True

        return False

    except Exception:
        traceback.print_exc()
        return False

# -------------------------
# LOGIC
# -------------------------
def reply(text):
    text = text.lower().strip()

    if text == "list":
        tasks = pending_tasks()
        if not tasks:
            return jesse("No pending jobs.")
        return jesse("Tasks:\n- " + "\n- ".join(extract_title(t) for t in tasks))

    if text == "focus":
        task = top_task()
        return jesse(f"Do this → {task}") if task else jesse("No tasks.")

    if text.startswith("add "):
        save_task(text[4:])
        return jesse("Task added.")

    if text.startswith("done "):
        ok = mark_done(text[5:])
        return jesse("Marked done." if ok else "Couldn't find task.")

    if text == "help":
        return jesse("add, list, done, focus")

    return jesse("Noted.")

# -------------------------
# GIF SENDER
# -------------------------
async def send_gif(update: Update, key: str):
    try:
        file_id = JESSE_GIFS.get(key) or random.choice(DEFAULT_GIFS)
        await update.message.reply_animation(animation=file_id)
    except:
        pass

# -------------------------
# HANDLER
# -------------------------
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = update.message.text.strip()

        gif = None

        if text.lower().startswith("add "):
            gif = "add"
        elif text.lower().startswith("done "):
            gif = "done"
        elif text.lower() == "focus":
            gif = "focus"

        response = reply(text)

        if gif:
            await send_gif(update, gif)

        await update.message.reply_text(response)

    except Exception:
        traceback.print_exc()

# -------------------------
# RUN
# -------------------------
def main():
    print("RUNNING BOT")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    app.run_polling()

if __name__ == "__main__":
    main()
