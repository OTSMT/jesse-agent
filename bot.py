import os
import random
import traceback

from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters
from notion_client import Client

# -------------------------
# ENV
# -------------------------
print("🔥 BOT FILE LOADED")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
NOTION_DB_ID = os.getenv("NOTION_DB_ID")

if not TELEGRAM_TOKEN or not NOTION_API_KEY or not NOTION_DB_ID:
    raise ValueError("Missing env vars")

# -------------------------
# NOTION
# -------------------------
notion = Client(auth=NOTION_API_KEY)
print("✅ Notion client initialized")

# -------------------------
# STYLE
# -------------------------
def jesse(text):
    return random.choice(["Yo. ", "Alright. ", "Bruh, ", "Listen. "]) + text + " yo."

# -------------------------
# NOTION FETCH (FINAL DIAGNOSTIC)
# -------------------------
def get_tasks():
    try:
        results = notion.databases.query(
            database_id=NOTION_DB_ID,
            filter={}  # no filters
        )

        # 🔥 CRITICAL DEBUG OUTPUT
        print("\n========== NOTION RAW RESPONSE ==========")
        print("RESULT COUNT:", len(results.get("results", [])))
        print(results)
        print("=========================================\n")

        tasks = []

        for r in results.get("results", []):
            props = r.get("properties", {})

            # Your confirmed column names
            title = "NO TITLE"
            title_prop = props.get("Task Type", {}).get("title", [])
            if title_prop:
                title = title_prop[0].get("plain_text", "NO TITLE")

            status = ""
            status_obj = props.get("Status Type", {}).get("select", {})
            if status_obj:
                status = status_obj.get("name", "")

            tasks.append({
                "title": title,
                "status": status.lower().strip()
            })

        return tasks

    except Exception:
        print("💥 NOTION QUERY ERROR")
        traceback.print_exc()
        return []

# -------------------------
# FILTER
# -------------------------
def pending_tasks():
    tasks = get_tasks()
    return [t for t in tasks if t.get("status") != "done"]

def top_task():
    tasks = pending_tasks()
    return tasks[0]["title"] if tasks else None

# -------------------------
# LOGIC
# -------------------------
def reply_logic(text):
    text = text.lower().strip()

    if text == "focus":
        task = top_task()
        return jesse(f"Do this → {task}") if task else jesse("No tasks.")

    if text == "list":
        tasks = pending_tasks()
        if not tasks:
            return jesse("No pending jobs.")
        return jesse("Backlog:\n- " + "\n- ".join(t["title"] for t in tasks))

    if text.startswith("add "):
        notion.pages.create(
            parent={"database_id": NOTION_DB_ID},
            properties={
                "Task Type": {"title": [{"text": {"content": text[4:]}}]},
                "Status Type": {"select": {"name": "Pending"}},
            },
        )
        return jesse("Task added.")

    return jesse("Noted.")

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
        print("💥 HANDLER CRASH")
        traceback.print_exc()

# -------------------------
# MAIN
# -------------------------
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

    print("🔥 Jesse OS RUNNING")
    app.run_polling()

if __name__ == "__main__":
    main()
