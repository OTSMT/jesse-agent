import os
import random
import traceback
import sys

from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters
from notion_client import Client

# -------------------------
# ENV
# -------------------------
print("🔥 BOT STARTING")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
NOTION_DB_ID = os.getenv("NOTION_DB_ID")

if not TELEGRAM_TOKEN:
    raise ValueError("Missing TELEGRAM_TOKEN")
if not NOTION_API_KEY:
    raise ValueError("Missing NOTION_API_KEY")
if not NOTION_DB_ID:
    raise ValueError("Missing NOTION_DB_ID")

# -------------------------
# NOTION CLIENT
# -------------------------
notion = Client(auth=NOTION_API_KEY)
print("✅ Notion client ready")

# -------------------------
# JESSE STYLE
# -------------------------
def jesse(text):
    return f"Yo. {text} yo."

# -------------------------
# DEBUG SAFE NOTION READ
# -------------------------
def get_tasks():
    try:
        print("\n📡 QUERYING NOTION DATABASE...")
        results = notion.databases.query(database_id=NOTION_DB_ID)

        print(f"📦 RAW RESULT COUNT: {len(results.get('results', []))}")

        tasks = []

        for r in results["results"]:
            props = r.get("properties", {})

            # TITLE
            title = "NO TITLE"

            task_prop = props.get("Task", {})
            title_arr = task_prop.get("title", [])

            if title_arr:
                title = title_arr[0].get("plain_text", "NO TITLE")

            # STATUS
            status_obj = props.get("Status", {}).get("select")
            status = status_obj.get("name") if status_obj else "EMPTY"

            print(f"➡ TASK: {title} | STATUS: {status}")

            tasks.append({
                "title": title,
                "status": status
            })

        print(f"📊 PARSED TASK COUNT: {len(tasks)}\n")

        return tasks

    except Exception:
        print("💥 NOTION READ FAILED")
        traceback.print_exc()
        return []

# -------------------------
# FILTER
# -------------------------
def pending_tasks():
    tasks = get_tasks()

    return [
        t for t in tasks
        if "pending" in str(t.get("status", "")).lower()
    ]

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
                "Task": {"title": [{"text": {"content": task}}]},
                "Status": {"select": {"name": "Pending"}},
            },
        )
        print(f"✅ CREATED TASK: {task}")
    except Exception:
        print("💥 CREATE FAILED")
        traceback.print_exc()

# -------------------------
# MARK DONE
# -------------------------
def mark_done(task_name):
    try:
        results = notion.databases.query(
            database_id=NOTION_DB_ID,
            filter={
                "property": "Task",
                "title": {"contains": task_name}
            }
        )

        if not results["results"]:
            return False

        page_id = results["results"][0]["id"]

        notion.pages.update(
            page_id=page_id,
            properties={"Status": {"select": {"name": "Done"}}}
        )

        return True

    except Exception:
        traceback.print_exc()
        return False

# -------------------------
# LOGIC
# -------------------------
def reply_logic(text):
    text = text.lower().strip()

    if text == "list":
        tasks = pending_tasks()
        if not tasks:
            return jesse("No pending tasks found.")
        return jesse("\n- " + "\n- ".join(t["title"] for t in tasks))

    if text == "focus":
        task = top_task()
        return jesse(f"Focus on → {task}" if task else "No tasks.")

    if text.startswith("add "):
        save_task(text[4:])
        return jesse("Task added.")

    return jesse("add, list, focus")

# -------------------------
# HANDLER
# -------------------------
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        msg = update.message
        if not msg:
            return

        text = msg.text.strip()

        reply = reply_logic(text)

        await msg.reply_text(reply)

    except Exception:
        traceback.print_exc()

# -------------------------
# MAIN
# -------------------------
def main():
    print("🚀 BOT RUNNING")

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

    app.run_polling()

# -------------------------
# ENTRY
# -------------------------
if __name__ == "__main__":
    main()
