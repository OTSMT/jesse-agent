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
# JESSE STYLE (UNCHANGED)
# -------------------------
def jesse(text):
    return random.choice(["Yo. ", "Alright. ", "Listen. ", "Bruh, "]) + text + " yo."

# -------------------------
# NOTION SAFE FETCH
# -------------------------
def get_tasks():
    try:
        results = notion.databases.query(database_id=NOTION_DB_ID)
        return results.get("results", [])
    except Exception:
        traceback.print_exc()
        return []

# -------------------------
# PARSE TASK TITLE (ROBUST)
# -------------------------
def extract_title(page):
    try:
        props = page.get("properties", {})
        for prop in props.values():
            if prop.get("type") == "title":
                title_arr = prop.get("title", [])
                if title_arr:
                    return title_arr[0].get("plain_text", "UNKNOWN")
        return "UNKNOWN"
    except:
        return "UNKNOWN"

# -------------------------
# PARSE STATUS
# -------------------------
def extract_status(page):
    try:
        props = page.get("properties", {})
        for prop in props.values():
            if prop.get("type") == "select":
                sel = prop.get("select")
                if sel:
                    return sel.get("name", "").lower()
        return ""
    except:
        return ""

# -------------------------
# FILTERS (UNCHANGED LOGIC)
# -------------------------
def pending_tasks():
    tasks = get_tasks()
    return [
        t for t in tasks
        if extract_status(t) != "done"
    ]

def top_task():
    tasks = pending_tasks()
    if not tasks:
        return None
    return extract_title(tasks[0])

# -------------------------
# SAVE TASK (UNCHANGED LOGIC)
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
    except Exception:
        traceback.print_exc()

# -------------------------
# MARK DONE (UNCHANGED LOGIC)
# -------------------------
def mark_done(task_name):
    try:
        results = notion.databases.query(database_id=NOTION_DB_ID)

        for page in results.get("results", []):
            title = extract_title(page)

            if task_name.lower() in title.lower():
                notion.pages.update(
                    page_id=page["id"],
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
# CORE LOGIC (UNCHANGED)
# -------------------------
def reply_logic(text):
    text = text.lower().strip()

    if text == "focus":
        task = top_task()
        return jesse(f"Do this right now → {task}") if task else jesse("No tasks. You're free.")

    if text == "today":
        tasks = pending_tasks()[:3]
        if not tasks:
            return jesse("Nothing on your plate.")
        return jesse("Top priorities:\n- " + "\n- ".join(extract_title(t) for t in tasks))

    if text.startswith("add "):
        save_task(text[4:].strip())
        return jesse("Task added.")

    if text == "list":
        tasks = pending_tasks()
        if not tasks:
            return jesse("No pending jobs.")
        return jesse("Your backlog:\n- " + "\n- ".join(extract_title(t) for t in tasks))

    if text == "help":
        return jesse("add <task>, done <task>, focus, today, list, db")

    return jesse(random.choice(["Noted.", "Alright.", "Got it.", "Say less.", "I'm tracking it."]))

# -------------------------
# HANDLER (UNCHANGED + DEBUG ADDED)
# -------------------------
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        msg = update.message
        if not msg or not msg.text:
            return

        text = msg.text.strip()

        gif_key = None

        # -------------------------
        # TEMP DEBUG COMMAND (IMPORTANT)
        # -------------------------
        if text.lower() == "db":
            try:
                db = notion.databases.retrieve(database_id=NOTION_DB_ID)
                props = db.get("properties", {})
                title = db.get("title", [])

                await msg.reply_text(
                    jesse(
                        "DB OK → " + str(title) +
                        "\nPROPERTIES → " + ", ".join(props.keys())
                    )
                )
                return
            except Exception as e:
                await msg.reply_text(jesse(f"DB ERROR → {repr(e)}"))
                return

        # -------------------------
        # GIF LOGIC (UNCHANGED BEHAVIOR)
        # -------------------------
        if text.lower().startswith("add "):
            gif_key = "add"
        elif text.lower() == "focus":
            gif_key = "focus"
        elif text.lower().startswith("done "):
            gif_key = "done"

        # -------------------------
        # RESPONSE
        # -------------------------
        reply = reply_logic(text)

        await msg.reply_text(reply)

    except Exception:
        traceback.print_exc()

# -------------------------
# MAIN (UNCHANGED)
# -------------------------
def main():
    print("RUNNING BOT")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    app.run_polling()

if __name__ == "__main__":
    main()
