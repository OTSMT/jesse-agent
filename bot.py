import os
import random
import traceback

from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters
from notion_client import Client

# -------------------------
# ENV
# -------------------------
print("🔥 BOT FILE LOADED")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
NOTION_DB_ID = os.getenv("NOTION_DB_ID")

if not TELEGRAM_TOKEN or not NOTION_API_KEY or not NOTION_DB_ID:
    raise ValueError("Missing env vars")

# -------------------------
# NOTION
# -------------------------
notion = Client(auth=NOTION_API_KEY)
print("✅ Notion client initialized")

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

# -------------------------
# STYLE
# -------------------------
def jesse(text):
    return random.choice(["Yo. ", "Alright. ", "Bruh, ", "Listen. "]) + text + " yo."

# -------------------------
# GIF SENDER (SAFE)
# -------------------------
async def send_gif(update: Update, key: str):
    try:
        if not update.message:
            return

        file_id = JESSE_GIFS.get(key)

        if not file_id:
            return

        try:
            await update.message.reply_animation(animation=file_id)
        except Exception:
            # fallback: no crash if Telegram rejects GIF
            print("[GIF WARNING] failed to send gif")

    except Exception:
        print("[GIF ERROR]")
        traceback.print_exc()

# -------------------------
# NOTION FETCH (STABLE)
# -------------------------
def get_tasks():
    try:
        results = notion.databases.query(database_id=NOTION_DB_ID)

        tasks = []

        for r in results.get("results", []):
            props = r.get("properties", {})

            # IMPORTANT: your real column names
            title_prop = props.get("Task Type", {}).get("title", [])
            title = title_prop[0].get("plain_text") if title_prop else "UNKNOWN TASK"

            status_obj = props.get("Status Type", {}).get("select")
            status = status_obj.get("name") if status_obj else ""

            tasks.append({
                "title": title,
                "status": status.lower().strip()
            })

        return tasks

    except Exception:
        print("💥 NOTION ERROR")
        traceback.print_exc()
        return []

# -------------------------
# FILTER
# -------------------------
def pending_tasks():
    tasks = get_tasks()
    return [t for t in tasks if t.get("status") != "done"]

def top_task():
    tasks = pending_tasks()
    return tasks[0]["title"] if tasks else None

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
        return jesse("Backlog:\n- " + "\n- ".join(t["title"] for t in tasks))

    if text.startswith("add "):
        notion.pages.create(
            parent={"database_id": NOTION_DB_ID},
            properties={
                "Task Type": {"title": [{"text": {"content": text[4:]}}]},
                "Status Type": {"select": {"name": "Pending"}},
            },
        )
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

        if text.lower().startswith("add "):
            gif_key = "add"
        elif text.lower() == "focus":
            gif_key = "focus"
        elif text.lower().startswith("done "):
            gif_key = "done"

        reply = reply_logic(text)

        await send_gif(update, gif_key)
        await msg.reply_text(reply)

    except Exception:
        print("💥 HANDLER CRASH")
        traceback.print_exc()

# -------------------------
# MAIN
# -------------------------
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

    print("🔥 Jesse OS RUNNING")
    app.run_polling()

if __name__ == "__main__":
    main()
