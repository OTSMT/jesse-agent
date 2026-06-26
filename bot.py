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
# NOTION CLIENT
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
# NOTION FETCH
# -------------------------
def get_tasks():
    try:
        results = notion.databases.query(
            database_id=NOTION_DB_ID,
            page_size=100
        )

        tasks = []

        for r in results.get("results", []):
            props = r.get("properties", {})

            # TITLE (Task)
            task_prop = props.get("Task", {}).get("title", [])
            title = task_prop[0].get("plain_text") if task_prop else "UNKNOWN TASK"

            # STATUS (Status)
            status_obj = props.get("Status", {}).get("select")
            status = status_obj.get("name") if status_obj else "Pending"

            tasks.append({
                "title": title,
                "status": status,
                "id": r["id"]
            })

        return tasks

    except Exception:
        print("NOTION FETCH ERROR")
        traceback.print_exc()
        return []

# -------------------------
# FILTERS (FIXED)
# -------------------------
def pending_tasks():
    tasks = get_tasks()
    cleaned = []

    for t in tasks:
        status = (t.get("status") or "").strip().lower()
        if status != "done":
            cleaned.append(t)

    return cleaned

def top_task():
    tasks = pending_tasks()
    return tasks[0]["title"] if tasks else None

# -------------------------
# SAVE TASK
# -------------------------
def save_task(task):
    try:
        notion.pages.create(
            parent={"database_id": NOTION_DB_ID},
            properties={
                "Task": {
                    "title": [{"text": {"content": task}}]
                },
                "Status": {
                    "select": {"name": "Pending"}
                },
            },
        )
        return True

    except Exception:
        print("CREATE ERROR")
        traceback.print_exc()
        return False

# -------------------------
# MARK DONE (FIXED MATCHING)
# -------------------------
def mark_done(task_name):
    try:
        tasks = get_tasks()

        search = task_name.strip().lower()

        for t in tasks:
            title = (t["title"] or "").strip().lower()

            if search in title or title in search:
                notion.pages.update(
                    page_id=t["id"],
                    properties={
                        "Status": {
                            "select": {"name": "Done"}
                        }
                    },
                )
                return True

        return False

    except Exception:
        print("DONE ERROR")
        traceback.print_exc()
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
        return jesse("Task added.") if ok else jesse("Failed to add task.")

    if text.startswith("done "):
        ok = mark_done(text[5:].strip())
        return jesse("Task done.") if ok else jesse("Couldn't find task.")

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
