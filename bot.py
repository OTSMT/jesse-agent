import os
import random
import traceback

from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters
from notion_client import Client

# -------------------------
# ENV
# -------------------------

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
# JESSE PERSONALITY LAYER 🔥
# -------------------------

def jesse(text):
    openings = [
        "Yo.",
        "Alright.",
        "Listen.",
        "Okay, so.",
        "Damn."
    ]

    endings = [
        "",
        " bitch.",
        " man.",
        " alright?",
        " got it?"
    ]

    return f"{random.choice(openings)} {text}{random.choice(endings)}"


def jesse_reply(text):
    text = text.lower().strip()

    # HELP
    if text == "help":
        return jesse(
            "Commands: add <task>, done <task>, focus, today, list"
        )

    # FOCUS
    if text == "focus":
        task = top_task()
        if not task:
            return jesse("No tasks. You're free for once.")

        return jesse(f"Do this right now → {task}")

    # TODAY
    if text == "today":
        tasks = pending_tasks()[:3]
        if not tasks:
            return jesse("Nothing on your plate.")

        return jesse(
            "Top priorities:\n- " + "\n- ".join([t["title"] for t in tasks])
        )

    # LIST
    if text == "list":
        tasks = pending_tasks()
        if not tasks:
            return jesse("No pending jobs.")

        return jesse(
            "Your backlog:\n- " + "\n- ".join([t["title"] for t in tasks])
        )

    # ENERGY (disabled but still funny)
    if text.startswith("energy"):
        return jesse("Energy system is locked. You're on your own vibe.")

    return jesse(random.choice([
        "Noted.",
        "Alright, I got it.",
        "I'll keep track of it.",
        "Say less."
    ]))


# -------------------------
# NOTION CORE
# -------------------------

def get_tasks():
    results = notion.databases.query(database_id=NOTION_DB_ID)

    tasks = []
    for r in results["results"]:
        try:
            title = r["properties"]["Task"]["title"][0]["text"]["content"]
            status = r["properties"]["Status"]["select"]["name"]

            tasks.append({
                "title": title,
                "status": status
            })
        except:
            continue

    return tasks


def pending_tasks():
    return [t for t in get_tasks() if t["status"] == "Pending"]


def top_task():
    tasks = pending_tasks()
    return tasks[0]["title"] if tasks else None


def save_task(task):
    notion.pages.create(
        parent={"database_id": NOTION_DB_ID},
        properties={
            "Task": {"title": [{"text": {"content": task}}]},
            "Status": {"select": {"name": "Pending"}}
        }
    )


def mark_done(task_name):
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


# -------------------------
# TELEGRAM HANDLER
# -------------------------

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    # ADD TASK
    if text.lower().startswith("add "):
        try:
            save_task(text[4:].strip())
            reply = jesse("Task added.")

        except:
            traceback.print_exc()
            reply = jesse("Failed to save task.")

    # DONE TASK
    elif text.lower().startswith("done "):
        try:
            ok = mark_done(text[5:].strip())
            reply = jesse("Task completed.") if ok else jesse("Couldn't find that task.")

        except:
            traceback.print_exc()
            reply = jesse("Update failed.")

    # EVERYTHING ELSE
    else:
        reply = jesse_reply(text)

    await update.message.reply_text(reply)


# -------------------------
# START BOT
# -------------------------

app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

print("🔥 Jesse OS v5.6 (Jesse Personality Edition) running")
app.run_polling()
