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
# SIMPLE PRIORITY ENGINE (NO CRASH RISK)
# -------------------------

def pending_tasks():
    return [t for t in get_tasks() if t["status"] == "Pending"]


def top_task():
    tasks = pending_tasks()
    if not tasks:
        return None

    # simple stable logic (NO scheduler, NO files)
    return tasks[0]["title"]


# -------------------------
# JESSE BRAIN (STABLE)
# -------------------------

def jesse_reply(text):
    text = text.lower().strip()

    if text == "focus":
        task = top_task()
        if not task:
            return "No tasks. You're free."

        return f"🎯 Focus on:\n👉 {task}"

    if text == "today":
        tasks = pending_tasks()[:3]
        if not tasks:
            return "Nothing to do."

        return "Today:\n- " + "\n- ".join([t["title"] for t in tasks])

    if text == "list":
        tasks = pending_tasks()
        if not tasks:
            return "No tasks."

        return "Tasks:\n- " + "\n- ".join([t["title"] for t in tasks])

    if text.startswith("energy"):
        return "Energy mode removed in safe version (restart later for upgrade)."

    return random.choice(["Noted.", "Alright.", "Got it.", "Say less."])


# -------------------------
# HANDLER
# -------------------------

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if text.lower().startswith("add "):
        try:
            save_task(text[4:].strip())
            reply = "Added."
        except:
            traceback.print_exc()
            reply = "Failed."

    elif text.lower().startswith("done "):
        try:
            ok = mark_done(text[5:].strip())
            reply = "Done." if ok else "Not found."
        except:
            traceback.print_exc()
            reply = "Failed."

    else:
        reply = jesse_reply(text)

    await update.message.reply_text(reply)


# -------------------------
# START
# -------------------------

app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

print("🔥 Jesse OS SAFE MODE running")
app.run_polling()
