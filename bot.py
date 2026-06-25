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

# -------------------------
# NOTION
# -------------------------
notion = Client(auth=NOTION_API_KEY)

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
# NOTION FETCH (STABLE + SIMPLE)
# -------------------------
def get_tasks():
    try:
        results = notion.databases.query(database_id=NOTION_DB_ID)

        tasks = []

        for r in results.get("results", []):
            props = r.get("properties", {})

            title_prop = props.get("Task Type", {}).get("title", [])
            title = title_prop[0].get("plain_text") if title_prop else "UNKNOWN TASK"

            status_obj = props.get("Status Type", {}).get("select")
            status = status_obj.get("name") if status_obj else ""

            tasks.append({
                "title": title,
                "status": status.lower().strip()
            })

        print("TASK COUNT:", len(tasks))
        return tasks

    except Exception:
        print("NOTION ERROR")
        traceback.print_exc()
        return []

# -------------------------
# FILTER (NO EDGE CASES)
# -------------------------
def pending_tasks():
    tasks = get_tasks()
    return [t for t in tasks if t["status"] != "done"]

# -------------------------
# ACTIONS
# -------------------------
def save_task(task):
    notion.pages.create(
        parent={"database_id": NOTION_DB_ID},
        properties={
            "Task Type": {"title": [{"text": {"content": task}}]},
            "Status Type": {"select": {"name": "Pending"}},
        },
    )

def top_task():
    tasks = pending_tasks()
    return tasks[0]["title"] if tasks else None

# -------------------------
# GIF SENDER (SAFE)
# -------------------------
async def send_gif(update: Update, key: str):
    try:
        if not update.message:
            return

        file_id = JESSE_GIFS.get(key) or random.choice(DEFAULT_GIFS)

        if file_id:
            await update.message.reply_animation(animation=file_id)

    except Exception:
        print("GIF ERROR")
        traceback.print_exc()

# -------------------------
# LOGIC
# -------------------------
def reply_logic(text):
    text = text.lower().strip()

    if text == "list":
        tasks = pending_tasks()
        if not tasks:
            return jesse("No tasks.")
        return jesse("Backlog:\n- " + "\n- ".join(t["title"] for t in tasks))

    if text == "focus":
        task = top_task()
        return jesse(f"Do this → {task}") if task else jesse("No tasks.")

    if text.startswith("add "):
        save_task(text[4:].strip())
        return jesse("Task added.")

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
        elif text == "focus":
            gif_key = "focus"

        reply = reply_logic(text)

        await send_gif(update, gif_key)
        await msg.reply_text(reply)

    except Exception:
        print("HANDLER ERROR")
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
