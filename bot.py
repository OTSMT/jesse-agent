import os
import random
import traceback

from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters
from notion_client import Client

# -------------------------
# ENV
# -------------------------
print("BOT STARTED")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
NOTION_API_KEY = os.getenv("NOTION_API_KEY")

# YOUR DB ID (FIXED)
NOTION_DB_ID = "7c3cad9121ab4194afc587cc1abcb5bb"

if not TELEGRAM_TOKEN or not NOTION_API_KEY:
    raise ValueError("Missing env vars")

print("USING DB:", NOTION_DB_ID)

# -------------------------
# NOTION
# -------------------------
notion = Client(auth=NOTION_API_KEY)

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

def jesse(text):
    return random.choice(["Yo. ", "Alright. ", "Listen. ", "Bruh, "]) + text + " yo."

# -------------------------
# NOTION SAFE FETCH (FIXED)
# -------------------------
def get_tasks():
    try:
        print("→ QUERY NOTION...")

        results = notion.databases.query(
            database_id=NOTION_DB_ID,
            page_size=100
        )

        tasks = []

        for r in results.get("results", []):
            props = r.get("properties", {})

            # TITLE (SAFE)
            title_data = props.get("Task", {}).get("title", [])
            title = "UNKNOWN"
            if title_data:
                title = title_data[0].get("plain_text", "UNKNOWN")

            # STATUS (SAFE)
            status_obj = props.get("Status", {}).get("select")
            status = status_obj.get("name") if status_obj else "Pending"

            tasks.append({
                "title": title,
                "status": status.lower(),
                "id": r["id"]
            })

        print(f"→ FOUND TASKS: {len(tasks)}")
        return tasks

    except Exception:
        print("NOTION FETCH ERROR")
        traceback.print_exc()
        return []

# -------------------------
# FILTER
# -------------------------
def pending_tasks():
    tasks = get_tasks()
    return [t for t in tasks if t["status"] != "done"]

def top_task():
    tasks = pending_tasks()
    return tasks[0]["title"] if tasks else None

# -------------------------
# ADD TASK
# -------------------------
def save_task(task):
    try:
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
        return True
    except Exception:
        print("CREATE ERROR")
        traceback.print_exc()
        return False

# -------------------------
# DONE TASK
# -------------------------
def mark_done(task_name):
    try:
        tasks = get_tasks()
        task_name = task_name.lower().strip()

        for t in tasks:
            if task_name in t["title"].lower():
                notion.pages.update(
                    page_id=t["id"],
                    properties={
                        "Status": {"select": {"name": "Done"}}
                    }
                )
                return True

        return False

    except Exception:
        print("DONE ERROR")
        traceback.print_exc()
        return False

# -------------------------
# REPLY LOGIC
# -------------------------
def reply_logic(text):
    text = text.lower().strip()

    if text == "debug":
        tasks = get_tasks()
        return jesse(f"DEBUG → {len(tasks)} tasks found")

    if text == "list":
        tasks = pending_tasks()
        if not tasks:
            return jesse("No tasks found.")
        return jesse("Tasks:\n- " + "\n- ".join(t["title"] for t in tasks))

    if text.startswith("add "):
        ok = save_task(text[4:])
        return jesse("Added.") if ok else jesse("Failed.")

    if text.startswith("done "):
        ok = mark_done(text[5:])
        return jesse("Done.") if ok else jesse("Not found.")

    if text == "focus":
        task = top_task()
        return jesse(f"Do this → {task}") if task else jesse("No tasks.")

    return jesse("Noted.")

# -------------------------
# HANDLER
# -------------------------
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        msg = update.message
        if not msg:
            return

        text = msg.text

        gif_key = None
        if text.lower().startswith("add "):
            gif_key = "add"
        elif text.lower().startswith("done "):
            gif_key = "done"
        elif text.lower() == "focus":
            gif_key = "focus"

        reply = reply_logic(text)

        if gif_key:
            file_id = JESSE_GIFS.get(gif_key)
            if file_id:
                await msg.reply_animation(file_id)

        await msg.reply_text(reply)

    except Exception:
        traceback.print_exc()

# -------------------------
# MAIN
# -------------------------
def main():
    print("RUNNING BOT")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    app.run_polling()

if __name__ == "__main__":
    main()
