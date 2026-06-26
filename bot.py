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
# DEBUG NOTION
# -------------------------
def debug_notion():
    try:
        db = notion.databases.retrieve(database_id=NOTION_DB_ID)
        props = db.get("properties", {})

        lines = ["📦 NOTION DATABASE SCHEMA:"]

        for name, info in props.items():
            lines.append(f"- {name} → {info.get('type')}")

        results = notion.databases.query(
            database_id=NOTION_DB_ID,
            page_size=5
        )

        lines.append("\n📋 SAMPLE TASKS:")

        for r in results.get("results", []):
            title = "UNKNOWN"

            for _, v in r.get("properties", {}).items():
                if v.get("type") == "title":
                    t = v.get("title", [])
                    if t:
                        title = t[0].get("plain_text", "UNKNOWN")

            lines.append(f"- {title}")

        return "\n".join(lines)

    except Exception as e:
        return f"❌ DEBUG FAILED:\n{e}"

# -------------------------
# SAFE NOTION PARSING
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
        results = notion.databases.query(
            database_id=NOTION_DB_ID,
            page_size=100
        )

        tasks = []

        for r in results.get("results", []):
            props = r.get("properties", {})

            tasks.append({
                "title": extract_title(props),
                "status": extract_status(props)
            })

        return tasks

    except Exception as e:
        print("NOTION FETCH ERROR")
        print(e)
        traceback.print_exc()
        return []

# -------------------------
# FILTER
# -------------------------
def pending_tasks():
    return [t for t in get_tasks() if t.get("status") != "done"]

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
                "Task Type": {
                    "title": [{"text": {"content": task}}]
                },
                "Status Type": {
                    "select": {"name": "Pending"}
                }
            }
        )
        return True

    except Exception as e:
        print("CREATE FAILED")
        print(e)
        traceback.print_exc()
        return False

# -------------------------
# MARK DONE
# -------------------------
def mark_done(task_name):
    try:
        results = notion.databases.query(
            database_id=NOTION_DB_ID,
            filter={
                "property": "Task Type",
                "title": {"contains": task_name}
            }
        )

        if not results.get("results"):
            return False

        page_id = results["results"][0]["id"]

        notion.pages.update(
            page_id=page_id,
            properties={
                "Status Type": {
                    "select": {"name": "Done"}
                }
            }
        )

        return True

    except Exception as e:
        print("DONE ERROR")
        print(e)
        traceback.print_exc()
        return False

# -------------------------
# GIF SENDER
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

    if text == "debug":
        return debug_notion()

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
