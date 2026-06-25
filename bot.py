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
# JESSE STYLE
# -------------------------
def jesse(text):
    return f"Yo. {text} yo."

# -------------------------
# GIF SENDER (SAFE)
# -------------------------
async def send_gif(update: Update, key: str):
    try:
        file_id = JESSE_GIFS.get(key) or random.choice(DEFAULT_GIFS)

        if update.message and file_id:
            await update.message.reply_animation(animation=file_id)

        print(f"🎬 GIF SENT: {key}")

    except Exception:
        print("💥 GIF ERROR")
        traceback.print_exc()

# -------------------------
# NOTION READ (DEBUG SAFE)
# -------------------------
def get_tasks():
    try:
        print("📡 Querying Notion...")

        results = notion.databases.query(database_id=NOTION_DB_ID)

        print(f"📦 Raw results: {len(results.get('results', []))}")

        tasks = []

        for r in results["results"]:
            props = r.get("properties", {})

            # TITLE SAFE
            title = "NO TITLE"
            task_prop = props.get("Task", {})
            title_arr = task_prop.get("title", [])

            if title_arr:
                title = title_arr[0].get("plain_text", "NO TITLE")

            # STATUS SAFE
            status_obj = props.get("Status", {}).get("select")
            status = status_obj.get("name") if status_obj else ""

            print(f"➡ {title} | {status}")

            tasks.append({
                "title": title,
                "status": status
            })

        return tasks

    except Exception:
        print("💥 NOTION ERROR")
        traceback.print_exc()
        return []

# -------------------------
# FILTER
# -------------------------
def pending_tasks():
    tasks = get_tasks()
    return [t for t in tasks if "pending" in str(t.get("status", "")).lower()]

def top_task():
    tasks = pending_tasks()
    return tasks[0]["title"] if tasks else None

# -------------------------
# SAVE TASK
# -------------------------
def save_task(task):
    try:
        notion.pages.create(
           
