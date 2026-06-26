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
# DEBUG NOTION SCHEMA (RUNS ON START)
# -------------------------
def debug_database():
    try:
        db = notion.databases.retrieve(database_id=NOTION_DB_ID)

        print("\n==== NOTION DATABASE SCHEMA ====")
        print("TITLE:", db.get("title"))

        props = db.get("properties", {})
        for name, meta in props.items():
            print(f"- {name} ({meta.get('type')})")
        print("================================\n")

    except Exception as e:
        print("DEBUG FAILED")
        print(e)
        traceback.print_exc()

# -------------------------
# NOTION READ
# -------------------------
def get_tasks():
    try:
        print("→ Calling Notion...")

        results = notion.databases.query(
            database_id=NOTION_DB_ID,
            page_size=100
        )

        tasks = []

        for r in results.get("results", []):
            props = r.get("properties", {})

            # Try BOTH possible schema names (this is key fix)
            title_prop = (
                props.get("Task", {}).get("title", []) or
                props.get("Task Type", {}).get("title", [])
            )

            title = "UNKNOWN TASK"
            if title_prop:
                t = title_prop[0]
                title = (
                    t.get("plain_text")
                    or t.get("text", {}).get("content")
                    or "UNKNOWN TASK"
                )

            status_obj = (
                props.get("Status", {}).get("select")
                or props.get("Status Type", {}).get("select")
            )

            status = status_obj.get("name") if status_obj else "Pending"
            status = status.lower().strip()

            print(f"FOUND → {title} | {status}")

            tasks.append({
                "title": title,
                "status": status
            })

        print(f"→ TASK COUNT: {len(tasks)}")
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
    tasks = get_tasks()
    return [t for t in tasks if t.get("status") != "done"]

def top_task():
    tasks = pending_tasks()
    return tasks[0]["title"] if tasks else None

# -------------------------
# SAVE TASK
# -------------------------
def save_task(task):
    try:
        print(f"→ Saving task: {task}")

        result = notion.pages.create(
            parent={"database_id": NOTION_DB_ID},
            properties={
                # Try both naming styles safely
                "Task": {
                    "title": [{"text": {"content": task}}]
                },
                "Status": {
                    "select": {"name": "Pending"}
                },
            },
        )

        print("TASK CREATED:", result["id"])
        return True

    except Exception as e:
        print("CREATE FAILED")
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
            return jesse("No tasks found.")
        return jesse("Backlog:\n- " + "\n- ".join(t["title"] for t in tasks))

    if text == "focus":
        task = top_task()
        return jesse(f"Do this → {task}") if task else jesse("No tasks.")

    if text.startswith("add "):
        ok = save_task(text[4:].strip())
        return jesse("Task added.") if ok else jesse("Couldn't save task.")

    if text.startswith("done "):
        task_name = text[5:].strip()

        try:
            results = notion.databases.query(
                database_id=NOTION_DB_ID,
                filter={
                    "property": "Task",
                    "title": {"contains": task_name}
                }
            )

            if not results.get("results"):
                return jesse("Couldn't find task.")

            page_id = results["results"][0]["id"]

            notion.pages.update(
                page_id=page_id,
                properties={
                    "Status": {"select": {"name": "Done"}}
                }
            )

            return jesse("Task completed.")

        except Exception as e:
            print("DONE ERROR")
            print(e)
            traceback.print_exc()
            return jesse("Update failed.")

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
        print("HANDLER ERROR")
        traceback.print_exc()

# -------------------------
# MAIN
# -------------------------
def main():
    print("RUNNING BOT")

    debug_database()  # IMPORTANT

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

    app.run_polling()

if __name__ == "__main__":
    main()
