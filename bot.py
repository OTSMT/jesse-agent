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
# NOTION RAW INSPECTOR (IMPORTANT)
# -------------------------
def get_tasks_raw():
    try:
        db = notion.databases.retrieve(database_id=NOTION_DB_ID)
        results = notion.databases.query(database_id=NOTION_DB_ID)

        print("\n===== NOTION DEBUG =====")
        print("DB TITLE:", db.get("title"))
        print("RESULT COUNT:", len(results.get("results", [])))
        print("========================\n")

        return db, results

    except Exception:
        traceback.print_exc()
        return None, {"results": []}

# -------------------------
# SAFE TASK PARSER (NO HARD PROPERTY NAMES)
# -------------------------
def parse_tasks():
    _, results = get_tasks_raw()

    tasks = []

    for page in results.get("results", []):
        props = page.get("properties", {})

        title = "UNKNOWN"
        status = "pending"

        # Try to find title property dynamically
        for prop_name, prop_value in props.items():
            if prop_value.get("type") == "title":
                t = prop_value.get("title", [])
                if t:
                    title = t[0].get("plain_text", "UNKNOWN")

            if prop_value.get("type") == "select":
                sel = prop_value.get("select")
                if sel:
                    status = sel.get("name", "pending")

        tasks.append({
            "title": title,
            "status": status.lower(),
            "id": page.get("id")
        })

    return tasks

# -------------------------
# FILTERS
# -------------------------
def pending_tasks():
    return [t for t in parse_tasks() if t["status"] != "done"]

# -------------------------
# ACTIONS
# -------------------------
def save_task(task):
    try:
        notion.pages.create(
            parent={"database_id": NOTION_DB_ID},
            properties={
                "Task": {"title": [{"text": {"content": task}}]},
                "Status": {"select": {"name": "Pending"}}
            }
        )
        return True
    except Exception:
        traceback.print_exc()
        return False

def mark_done(task_name):
    try:
        tasks = parse_tasks()
        task_name = task_name.lower()

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
        db, results = get_tasks_raw()
        count = len(results.get("results", []))
        return jesse(f"DEBUG → tasks in DB response: {count}")

    if text == "dump":
        # THIS is the key tool now
        _, results = get_tasks_raw()
        return jesse(str(results)[:1500])

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

    return jesse("Noted.")

# -------------------------
# HANDLER
# -------------------------
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        msg = update.message
        if not msg:
            return

        reply = reply_logic(msg.text)

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
