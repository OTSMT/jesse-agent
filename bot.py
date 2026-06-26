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

# IMPORTANT: your DB id (unchanged)
NOTION_DB_ID = "7c3cad9121ab4194afc587cc1abcb5bb"

if not TELEGRAM_TOKEN or not NOTION_API_KEY:
    raise ValueError("Missing env vars")

notion = Client(auth=NOTION_API_KEY)

# -------------------------
# JESSE STYLE
# -------------------------
def jesse(text):
    return random.choice(["Yo. ", "Alright. ", "Listen. ", "Bruh, "]) + text + " yo."

# -------------------------
# NOTION DEBUG + FETCH
# -------------------------
def get_tasks(debug=False):
    try:
        db = notion.databases.retrieve(database_id=NOTION_DB_ID)

        title = db.get("title", [])
        db_name = title[0]["plain_text"] if title else "UNKNOWN"

        results = notion.databases.query(database_id=NOTION_DB_ID)

        tasks = []

        for r in results.get("results", []):
            props = r.get("properties", {})

            # SAFE TITLE DETECTION
            title_prop = props.get("Task", {}).get("title", [])
            title = title_prop[0].get("plain_text") if title_prop else "UNKNOWN"

            # SAFE STATUS DETECTION
            status_obj = props.get("Status", {}).get("select")
            status = status_obj.get("name") if status_obj else "Pending"

            tasks.append({
                "title": title,
                "status": status.lower(),
                "id": r["id"]
            })

        if debug:
            print("DB NAME:", db_name)
            print("TASK COUNT:", len(tasks))

        return db_name, tasks

    except Exception:
        traceback.print_exc()
        return "ERROR", []

# -------------------------
# FILTERS
# -------------------------
def pending_tasks():
    _, tasks = get_tasks()
    return [t for t in tasks if t["status"] != "done"]

def top_task():
    tasks = pending_tasks()
    return tasks[0]["title"] if tasks else None

# -------------------------
# SAVE
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
                }
            }
        )
        return True
    except Exception:
        traceback.print_exc()
        return False

# -------------------------
# DONE
# -------------------------
def mark_done(task_name):
    try:
        _, tasks = get_tasks()

        task_name = task_name.lower().strip()

        for t in tasks:
            if task_name in t["title"].lower():
                notion.pages.update(
                    page_id=t["id"],
                    properties={
                        "Status": {"select": {"name": "Done"}}
                    }
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

    if text == "debug":
        db_name, tasks = get_tasks(debug=True)
        return jesse(f"DB: {db_name} | TASKS: {len(tasks)}")

    if text == "list":
        tasks = pending_tasks()
        if not tasks:
            return jesse("No tasks found.")
        return jesse("Tasks:\n- " + "\n- ".join(t["title"] for t in tasks))

    if text.startswith("add "):
        ok = save_task(text[4:])
        return jesse("Added.") if ok else jesse("Failed add.")

    if text.startswith("done "):
        ok = mark_done(text[5:])
        return jesse("Done.") if ok else jesse("Not found.")

    if text == "focus":
        task = top_task()
        return jesse(f"Do this → {task}") if task else jesse("No tasks.")

    return jesse("Noted.")

# -------------------------
# HANDLER
# -------------------------
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        msg = update.message
        if not msg:
            return

        text = msg.text

        reply = reply_logic(text)

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
