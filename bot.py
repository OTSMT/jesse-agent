import os
import random
import traceback

from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters
from notion_client import Client

# -------------------------
# ENV
# -------------------------
print("BOT STARTED")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
NOTION_DB_ID = os.getenv("NOTION_DB_ID")

if not TELEGRAM_TOKEN or not NOTION_API_KEY or not NOTION_DB_ID:
    raise ValueError("Missing env vars")

notion = Client(auth=NOTION_API_KEY)

# -------------------------
# JESSE GIFS
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
# LOAD DB SCHEMA ON START (IMPORTANT FIX)
# -------------------------
db_schema = notion.databases.retrieve(database_id=NOTION_DB_ID)
properties = db_schema["properties"]

TASK_PROP = None
STATUS_PROP = None

for name, prop in properties.items():
    if prop["type"] == "title":
        TASK_PROP = name
    if prop["type"] == "select":
        STATUS_PROP = name

print("==== SCHEMA DETECTED ====")
print("TASK_PROP:", TASK_PROP)
print("STATUS_PROP:", STATUS_PROP)

# -------------------------
# NOTION FETCH
# -------------------------
def get_tasks():
    try:
        return notion.databases.query(database_id=NOTION_DB_ID).get("results", [])
    except Exception:
        traceback.print_exc()
        return []

# -------------------------
# EXTRACT TITLE (SAFE)
# -------------------------
def extract_title(page):
    try:
        title_data = page["properties"][TASK_PROP]["title"]
        return title_data[0]["plain_text"] if title_data else "UNKNOWN"
    except:
        return "UNKNOWN"

# -------------------------
# EXTRACT STATUS (SAFE)
# -------------------------
def extract_status(page):
    try:
        sel = page["properties"][STATUS_PROP]["select"]
        return sel["name"].lower() if sel else ""
    except:
        return ""

# -------------------------
# FILTERS
# -------------------------
def pending_tasks():
    tasks = get_tasks()
    return [t for t in tasks if extract_status(t) != "done"]

def top_task():
    tasks = pending_tasks()
    return extract_title(tasks[0]) if tasks else None

# -------------------------
# SAVE TASK
# -------------------------
def save_task(task):
    try:
        notion.pages.create(
            parent={"database_id": NOTION_DB_ID},
            properties={
                TASK_PROP: {"title": [{"text": {"content": task}}]},
                STATUS_PROP: {"select": {"name": "Pending"}},
            },
        )
    except Exception:
        traceback.print_exc()

# -------------------------
# MARK DONE
# -------------------------
def mark_done(task_name):
    try:
        results = notion.databases.query(database_id=NOTION_DB_ID)

        for page in results["results"]:
            title = extract_title(page)

            if task_name.lower().strip() == title.lower().strip():
                notion.pages.update(
                    page_id=page["id"],
                    properties={
                        STATUS_PROP: {"select": {"name": "Done"}}
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
def reply_logic(text):
    text = text.lower().strip()

    if text == "focus":
        task = top_task()
        return jesse(f"Do this → {task}") if task else jesse("No tasks.")

    if text == "list":
        tasks = pending_tasks()
        if not tasks:
            return jesse("No pending jobs.")
        return jesse("Backlog:\n- " + "\n- ".join(extract_title(t) for t in tasks))

    if text.startswith("add "):
        save_task(text[4:].strip())
        return jesse("Task added.")

    if text == "help":
        return jesse("add, list, done, focus")

    return jesse("Noted.")

# -------------------------
# GIF
# -------------------------
async def send_gif(update: Update, key: str):
    try:
        if not update or not update.message:
            return

        file_id = JESSE_GIFS.get(key) or random.choice(DEFAULT_GIFS)
        await update.message.reply_animation(animation=file_id)

    except Exception:
        traceback.print_exc()

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

        if text.lower().startswith("add "):
            gif_key = "add"
        elif text.lower().startswith("done "):
            gif_key = "done"
        elif text.lower() == "focus":
            gif_key = "focus"

        if text.lower().startswith("done "):
            ok = mark_done(text[5:].strip())
            reply = jesse("Done." if ok else "Can't find it.")
        else:
            reply = reply_logic(text)

        await send_gif(update, gif_key)
        await msg.reply_text(reply)

    except Exception:
        traceback.print_exc()

# -------------------------
# MAIN
# -------------------------
def main():
    print("RUNNING BOT")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    app.run_polling()

if __name__ == "__main__":
    main()
