import os
import random
import traceback

from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters
from notion_client import Client

# ENV
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
NOTION_DB_ID = os.getenv("NOTION_DB_ID")

if not TELEGRAM_TOKEN:
    raise ValueError("Missing TELEGRAM_TOKEN")
if not NOTION_API_KEY:
    raise ValueError("Missing NOTION_API_KEY")
if not NOTION_DB_ID:
    raise ValueError("Missing NOTION_DB_ID")

notion = Client(auth=NOTION_API_KEY)


# -------------------------
# NOTION FUNCTIONS
# -------------------------

def save_task(task):
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


def mark_task_done(task_name):
    results = notion.databases.query(
        database_id=NOTION_DB_ID,
        filter={
            "property": "Task",
            "title": {
                "contains": task_name
            }
        }
    )

    if not results["results"]:
        return False

    page_id = results["results"][0]["id"]

    notion.pages.update(
        page_id=page_id,
        properties={
            "Status": {
                "select": {"name": "Done"}
            }
        }
    )

    return True


def list_tasks():
    results = notion.databases.query(
        database_id=NOTION_DB_ID,
        filter={
            "property": "Status",
            "select": {
                "equals": "Pending"
            }
        }
    )

    tasks = []
    for r in results["results"]:
        try:
            tasks.append(r["properties"]["Task"]["title"][0]["text"]["content"])
        except:
            continue

    return tasks


# -------------------------
# JESSE FREE BRAIN
# -------------------------

def jesse_reply(text):
    text = text.lower()

    if "list" in text:
        tasks = list_tasks()
        if not tasks:
            return "No pending jobs. You’re free, bitch."
        return "Pending tasks:\n- " + "\n- ".join(tasks)

    if "today" in text or "what should i do" in text:
        tasks = list_tasks()
        if not tasks:
            return "Nothing to do. That feels suspiciously peaceful."
        return f"Start with: {tasks[0]}"

    if "add " in text:
        return "Use: add <task>"

    if "done " in text:
        return "Use: done <task>"

    if "help" in text:
        return (
            "Commands:\n"
            "add <task>\n"
            "done <task>\n"
            "list\n"
            "today"
        )

    if "hello" in text or "hi" in text:
        return "Yo. Jesse OS online. What are we doing today?"

    if "tired" in text or "lazy" in text:
        return "Yeah. Still gotta do something small though, bitch."

    return random.choice([
        "Noted.",
        "Alright.",
        "Got it.",
        "I’m tracking it.",
        "Say less."
    ])


# -------------------------
# TELEGRAM HANDLER
# -------------------------

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    # ADD TASK
    if text.lower().startswith("add "):
        task = text[4:]

        try:
            save_task(task)
            reply = f"Added: {task}"

        except Exception:
            traceback.print_exc()
            reply = "Failed to save task."

    # DONE TASK
    elif text.lower().startswith("done "):
        task = text[5:]

        try:
            success = mark_task_done(task)
            reply = "Marked done." if success else "Task not found."

        except Exception:
            traceback.print_exc()
            reply = "Failed to update task."

    # OTHER COMMANDS
    else:
        reply = jesse_reply(text)

    await update.message.reply_text(reply)


# -------------------------
# START BOT
# -------------------------

app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

print("🔥 Jesse OS (FREE MODE) is running")
app.run_polling()
