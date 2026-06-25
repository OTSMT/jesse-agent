import os
import random
import traceback
import json
from datetime import datetime

from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters
from notion_client import Client
from apscheduler.schedulers.background import BackgroundScheduler

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
# STATE (persistent file memory)
# -------------------------

STATE_FILE = "jesse_state.json"

def load_state():
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except:
        return {
            "energy": "normal",
            "last_focus": None,
            "last_active": None
        }

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

STATE = load_state()

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
# AUTONOMY ENGINE
# -------------------------

def pending_tasks():
    return [t for t in get_tasks() if t["status"] == "Pending"]


def score(task):
    title = task["title"].lower()
    s = 0

    if "urgent" in title:
        s += 50
    if "important" in title:
        s += 30
    if "daily" in title:
        s += 20

    if STATE["energy"] == "low":
        s -= 10
    if STATE["energy"] == "high":
        s += 10

    return s


def top_tasks(n=3):
    tasks = pending_tasks()
    return sorted(tasks, key=score, reverse=True)[:n]


# -------------------------
# SCHEDULER ACTIONS
# -------------------------

def morning_brief():
    tasks = top_tasks(3)

    if not tasks:
        return "☀️ Morning: No tasks today."

    msg = "☀️ MORNING BRIEF\n\nTop priorities:\n"
    for i, t in enumerate(tasks, 1):
        msg += f"{i}) {t['title']}\n"

    return msg


def evening_summary():
    tasks = pending_tasks()

    return (
        "🌙 EVENING SUMMARY\n\n"
        f"Remaining tasks: {len(tasks)}\n"
        f"Energy mode: {STATE['energy']}"
    )


# -------------------------
# JESSE BRAIN v6
# -------------------------

def jesse_reply(text):
    text = text.lower().strip()

    if text == "focus":
        tasks = top_tasks(1)
        if not tasks:
            return "No tasks."

        STATE["last_focus"] = tasks[0]["title"]
        save_state(STATE)

        return f"🎯 FOCUS:\n{tasks[0]['title']}"

    if text == "today":
        tasks = top_tasks(3)
        if not tasks:
            return "Nothing to do."

        return "TODAY:\n- " + "\n- ".join([t["title"] for t in tasks])

    if text == "morning":
        return morning_brief()

    if text == "evening":
        return evening_summary()

    if text.startswith("energy "):
        mode = text.replace("energy ", "").strip()
        if mode in ["low", "normal", "high"]:
            STATE["energy"] = mode
            save_state(STATE)
            return f"Energy set to {mode}"
        return "Use: energy low/normal/high"

    if text == "stats":
        tasks = get_tasks()
        done = len([t for t in tasks if t["status"] == "Done"])
        return f"Done: {done} | Pending: {len(tasks)-done}"

    return random.choice(["Noted.", "Alright.", "Got it.", "Say less."])


# -------------------------
# TELEGRAM HANDLER
# -------------------------

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    STATE["last_active"] = datetime.utcnow().isoformat()
    save_state(STATE)

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
# SCHEDULER (REAL AUTONOMY)
# -------------------------

scheduler = BackgroundScheduler()

def send_morning():
    print(morning_brief())

def send_evening():
    print(evening_summary())

scheduler.add_job(send_morning, "cron", hour=9)
scheduler.add_job(send_evening, "cron", hour=21)

scheduler.start()


# -------------------------
# START BOT
# -------------------------

app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

print("🔥 Jesse OS v6 FULL AUTONOMY RUNNING")
app.run_polling()
