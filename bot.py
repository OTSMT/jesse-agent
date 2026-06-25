import os
import random
import traceback
import sys
import time

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
# JESSE GIFS
# -------------------------

JESSE_GIFS = {
    "add": "CgACAgQAAxkBAANxaj0LFl0u4HHc0CpZWroUYFZ8loAAAtUCAAJVlQxTBkmzB2EPQCo8BA",
    "done": "CgACAgQAAxkBAANyaj0LJVuPaT_cfd4RvqIivMF4vdMAAv4CAAKzsAxTGIFPam3qjak8BA",
    "focus": "CgACAgQAAxkBAANzaj0LQ3LnyEwYQ_aw8-CtZsA07l4AAhwHAAJ2b0VQAAFnz-zlNdQgPAQ",
    "default": None
}

DEFAULT_GIFS = [
    "CgACAgQAAxkBAANwaj0LDR9fIlU9WkEigLOHE5sV2wMAAiQDAAIqpyxTGZ0lrfl2IpQ8BA",
    "CgACAgQAAxkBAANuaj0K_bkzP8ZcOpEHDLI1WXXQtSYAAlgIAAIVdXxRISrlCSjFWs88BA",
    "CgACAgQAAxkBAANvaj0LBnguOITXUPIWodCIx7BUCGsAArYDAAKCb51QTuahwuylJAk8BA"
]

# -------------------------
# PERSONALITY
# -------------------------

def jesse(text):
    prefixes = ["Yo.", "Alright.", "Listen.", "Damn.", "Okay so."]
    suffixes = ["", " bitch.", " man.", " alright?", " got it?"]
    return f"{random.choice(prefixes)} {text}{random.choice(suffixes)}"

# -------------------------
# GIF SENDER (SAFE)
# -------------------------

async def send_gif(update: Update, key: str):

    if not update.message:
        return

    file_id = JESSE_GIFS.get(key) or random.choice(DEFAULT_GIFS)

    if not file_id:
        return

    try:
        await update.message.reply_animation(animation=file_id)
        print(f"[GIF SENT] {key}")
    except Exception:
        print("[GIF ERROR]")
        traceback.print_exc()

# -------------------------
# NOTION
# -------------------------

def get_tasks():
    results = notion.databases.query(database_id=NOTION_DB_ID)

    tasks = []

    for r in results["results"]:
        try:
            title = r["properties"]["Task"]["title"][0]["text"]["content"]
            status = r["properties"]["Status"]["select"]["name"]

            tasks.append({"title": title, "status": status})
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
# BRAIN
# -------------------------

def jesse_reply(text):

    text = text.lower().strip()

    if text == "focus":
        task = top_task()
        if not task:
            return jesse("No tasks. You're free.")
        return jesse(f"Do this right now → {task}")

    if text == "today":
        tasks = pending_tasks()[:3]
        if not tasks:
            return jesse("Nothing on your plate.")
        return jesse("Top priorities:\n- " + "\n- ".join([t["title"] for t in tasks]))

    if text == "list":
        tasks = pending_tasks()
        if not tasks:
            return jesse("No pending jobs.")
        return jesse("Your backlog:\n- " + "\n- ".join([t["title"] for t in tasks]))

    if text == "help":
        return jesse("add <task>, done <task>, focus, today, list")

    return jesse(random.choice([
        "Noted.",
        "Alright.",
        "Got it.",
        "Say less.",
        "I'm tracking it."
    ]))

# -------------------------
# DEBUG GIF LOGGER
# -------------------------

async def gif_debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        msg = update.message
        if msg and msg.animation:
            print("\n========== GIF ==========")
            print(msg.animation.file_id)
            print("=========================\n")
    except:
        traceback.print_exc()

# -------------------------
# HANDLER
# -------------------------

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):

    try:
        msg = update.message
        if not msg:
            return

        text = msg.text or msg.caption
        if not text:
            return

        text = text.strip()

        gif_key = "default"

        if text.lower().startswith("add "):
            task = text[4:].strip()
            save_task(task)
            gif_key = "add"
            reply = jesse("Task added.")

        elif text.lower().startswith("done "):
            task = text[5:].strip()
            ok = mark_done(task)
            gif_key = "done"

            if ok:
                reply = jesse("Task completed.")
            else:
                reply = jesse("Couldn't find that task.")

        elif text.lower() == "focus":
            gif_key = "focus"
            reply = jesse_reply(text)

        else:
            reply = jesse_reply(text)

        await send_gif(update, gif_key)
        await msg.reply_text(reply)

    except Exception:
        print("[HANDLER CRASH]")
        traceback.print_exc()

# -------------------------
# BOOT LOOP (CRASH-PROOF)
# -------------------------

def main():

    while True:
        try:
            print("🔥 Jesse OS starting...")

            app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

            # safer handlers
            app.add_handler(MessageHandler(filters.ANIMATION, gif_debug))
            app.add_handler(MessageHandler(filters.TEXT, handle))

            print("🔥 Jesse OS RUNNING")

            app.run_polling()

        except Exception as e:
            print("💥 BOT CRASHED - RESTARTING")
            traceback.print_exc()
            time.sleep(3)

# -------------------------
# ENTRY POINT
# -------------------------

if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
