import os
import random
import traceback
import sys

from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters
from notion_client import Client

# -------------------------
# STARTUP DEBUG (DO NOT REMOVE)
# -------------------------

print("🔥 BOT FILE LOADED")

# -------------------------
# ENVIRONMENT VARIABLES
# -------------------------

try:
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
    NOTION_API_KEY = os.getenv("NOTION_API_KEY")
    NOTION_DB_ID = os.getenv("NOTION_DB_ID")

    print("✅ ENV variables loaded")

    if not TELEGRAM_TOKEN:
        raise Exception("Missing TELEGRAM_TOKEN")
    if not NOTION_API_KEY:
        raise Exception("Missing NOTION_API_KEY")
    if not NOTION_DB_ID:
        raise Exception("Missing NOTION_DB_ID")

except Exception as e:
    print("💥 ENV ERROR:", e)
    sys.exit(1)

# -------------------------
# NOTION CLIENT
# -------------------------

try:
    notion = Client(auth=NOTION_API_KEY)
    print("✅ Notion client initialized")
except Exception:
    print("💥 NOTION INIT FAILED")
    traceback.print_exc()
    sys.exit(1)

# -------------------------
# JESSE PERSONALITY (UNCHANGED IDEA)
# -------------------------

def jesse(text):
    prefixes = ["Yo.", "Alright.", "Listen.", "Damn.", "Okay so."]
    suffixes = ["", " bitch.", " man.", " alright?", " got it?"]
    return f"{random.choice(prefixes)} {text}{random.choice(suffixes)}"

# -------------------------
# NOTION FUNCTIONS (UNCHANGED BEHAVIOR)
# -------------------------

def save_task(task):
    notion.pages.create(
        parent={"database_id": NOTION_DB_ID},
        properties={
            "Task": {"title": [{"text": {"content": task}}]},
            "Status": {"select": {"name": "Pending"}}
        }
    )

def get_tasks():
    try:
        results = notion.databases.query(database_id=NOTION_DB_ID)
        tasks = []

        for r in results["results"]:
            try:
                title = r["properties"]["Task"]["title"][0]["text"]["content"]
                status = r["properties"]["Status"]["select"]["name"]
                tasks.append((title, status))
            except:
                continue

        return tasks

    except Exception:
        print("💥 NOTION QUERY ERROR")
        traceback.print_exc()
        return []

# -------------------------
# BOT LOGIC (UNCHANGED INTENT)
# -------------------------

def reply_logic(text):
    text = text.lower().strip()

    if text.startswith("add "):
        task = text[4:]
        save_task(task)
        return jesse("Task added.")

    if text == "list":
        tasks = get_tasks()
        pending = [t[0] for t in tasks if t[1] == "Pending"]
        return jesse("\n".join(pending) if pending else "No tasks.")

    if text == "help":
        return jesse("add <task>, list")

    return jesse("Got it.")

# -------------------------
# HANDLER (SAFE)
# -------------------------

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        msg = update.message
        if not msg:
            return

        text = msg.text or msg.caption
        if not text:
            return

        reply = reply_logic(text)
        await msg.reply_text(reply)

    except Exception:
        print("💥 HANDLER CRASH")
        traceback.print_exc()

# -------------------------
# START BOT (VISIBLE + SAFE)
# -------------------------

if __name__ == "__main__":
    try:
        print("🚀 Starting bot...")

        app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

        app.add_handler(MessageHandler(filters.TEXT, handle))

        print("🤖 Bot is running")

        app.run_polling()

    except Exception:
        print("💥 BOT CRASH AT STARTUP")
        traceback.print_exc()
        sys.exit(1)
