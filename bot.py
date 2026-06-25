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
print("BOT FILE LOADED")

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
try:
    notion = Client(auth=NOTION_API_KEY)
    print("Notion client initialized")
except Exception:
    print("NOTION INIT FAILED")
    traceback.print_exc()
    sys.exit(1)

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
# PERSONALITY
# -------------------------
def jesse(text):
    prefixes = ["Yo.", "Alright.", "Listen.", "Yo man,", "Bruh,"]
    suffixes = ["yo.", "for real.", "cap.", "bitch.", "yo."]
    return f"{random.choice(prefixes)} {text} {random.choice(suffixes)}"

# -------------------------
# NOTION FETCH (FIXED)
# -------------------------
def get_tasks():
    try:
        results = notion.databases.query(database_id=NOTION_DB_ID)

        tasks = []

        for r in results.get("results", []):
            props = r.get("properties", {})

            # ✅ FIXED: matches your actual Notion DB
            title_prop = props.get("Task Type", {}).get("title", [])
            title = "UNKNOWN TASK"
            if title_prop:
                title = title_prop[0].get("plain_text", "UNKNOWN TASK")

            status_obj = props.get("Status Type", {}).get("select")
            status = status_obj.get("name") if status_obj else ""

            tasks.append({
                "title": title,
                "status": status.strip().lower()
            })

        return tasks

    except Exception:
        print("NOTION QUERY ERROR")
        traceback.print_exc()
        return []

# -------------------------
# FILTER
# -------------------------
def pending_tasks():
    tasks = get_tasks()
    return [t for t in tasks if (t.get("status") or "") != "done"]

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
                "Task Type": {"title": [{"text": {"content": task}}]},
                "Status Type": {"select": {"name": "Pending"}},
            },
        )
    except Exception:
        print("NOTION CREATE ERROR")
        traceback.print_exc()

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
                "Status Type": {"select": {"name": "Done"}}
            }
        )

        return True

    except Exception:
        print("NOTION UPDATE ERROR")
        traceback.print_exc()
        return False

# -------------------------
# LOGIC
# -------------------------
def reply_logic(text):
    text = text.lower().strip()

    if text == "focus":
        task = top_task()
        return jesse(f"Do this right now → {task}") if task else jesse("No tasks.")

    if text == "today":
        tasks = pending_tasks()[:3]
        if not tasks:
            return jesse("Nothing on your plate.")
        return jesse("Top priorities:\n- " + "\n- ".join([t["title"] for t in tasks]))

    if text.startswith("add "):
        save_task(text[4:].strip())
        return jesse("Task added.")

    if text == "list":
        tasks = pending_tasks()
        if not tasks:
            return jesse("No pending jobs.")
        return jesse("Your backlog:\n- " + "\n- ".join([t["title"] for t in tasks]))

    return jesse(random.choice(["Noted.", "Alright.", "Got it.", "Say less.", "I'm tracking it."]))

# -------------------------
# HANDLER
# -------------------------
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        msg = update.message
        if not msg or not msg.text:
            return

        text = msg.text.strip()

        reply = reply_logic(text)
        await msg.reply_text(reply)

    except Exception:
        print("HANDLER ERROR")
        traceback.print_exc()

# -------------------------
# MAIN
# -------------------------
def main():
    print("Jesse OS RUNNING")

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

    app.run_polling()

# -------------------------
# ENTRY
# -------------------------
if __name__ == "__main__":
    main()
