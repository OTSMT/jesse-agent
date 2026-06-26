import os
import random
import traceback

from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters
from notion_client import Client

print("BOT STARTED")

# -------------------------
# ENV
# -------------------------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
NOTION_DB_ID = os.getenv("NOTION_DB_ID")

if not TELEGRAM_TOKEN or not NOTION_API_KEY or not NOTION_DB_ID:
    raise ValueError("Missing env vars")

notion = Client(auth=NOTION_API_KEY)

# -------------------------
# JESSE STYLE
# -------------------------
def jesse(text):
    return random.choice(["Yo. ", "Alright. ", "Listen. ", "Bruh, "]) + text + " yo."

# -------------------------
# DEBUG ON START (IMPORTANT)
# -------------------------
try:
    db = notion.databases.retrieve(database_id=NOTION_DB_ID)
    print("==== DATABASE CONNECTED ====")
    print("Title:", db.get("title"))
    print("Properties:", list(db.get("properties", {}).keys()))
except Exception as e:
    print("❌ DATABASE ERROR")
    print(e)

# -------------------------
# NOTION FETCH (RAW DEBUG INCLUDED)
# -------------------------
def get_tasks():
    try:
        res = notion.databases.query(database_id=NOTION_DB_ID)
        print("==== RAW QUERY RESULT COUNT ====", len(res.get("results", [])))
        return res.get("results", [])
    except Exception as e:
        print("QUERY ERROR:", e)
        traceback.print_exc()
        return []

# -------------------------
# SAFE PROPERTY FINDERS
# -------------------------
def extract_title(page):
    props = page.get("properties", {})
    for v in props.values():
        if v.get("type") == "title":
            t = v.get("title", [])
            return t[0]["plain_text"] if t else "UNKNOWN"
    return "UNKNOWN"

def extract_status(page):
    props = page.get("properties", {})
    for v in props.values():
        if v.get("type") == "select":
            sel = v.get("select")
            if sel:
                return sel.get("name", "").lower()
    return ""

# -------------------------
# CORE FILTERS
# -------------------------
def pending_tasks():
    tasks = get_tasks()
    return [t for t in tasks if extract_status(t) != "done"]

def top_task():
    tasks = pending_tasks()
    return extract_title(tasks[0]) if tasks else None

# -------------------------
# WRITE TASK
# -------------------------
def save_task(text):
    try
