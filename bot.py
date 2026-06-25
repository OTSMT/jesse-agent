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
print("🔥 BOT FILE LOADED")

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
try:
    notion = Client(auth=NOTION_API_KEY)
    print("✅ Notion client initialized")
except Exception:
    print("💥 NOTION INIT FAILED")
    traceback.print_exc()
    sys.exit(1)

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
    prefixes = ["Yo.", "Alright.", "Listen.", "Yo man,", "Bruh,"]
    suffixes = ["yo.", "for real.", "cap.", "bitch.", "yo."]
    return f"{random.choice(prefixes)} {text} {random.choice(suffixes)}"

# -------------------------
# GIF SENDER
# -------------------------
async def send_gif(update: Update, key: str):
    if not update.message:
        return

    file_id = JESSE_GIFS.get(key) or random.choice(DEFAULT_GIFS)

    try:
        if file_id:
            await update.message.reply_animation(animation=file_id)
    except Exception:
        print("[GIF ERROR]")
        traceback.print_exc()

# -------------------------
# NOTION TASK PARSER (FIXED FOR ALL FORMATS)
# -------------------------
def get_tasks():
    try:
        results = notion.databases.query(database_id=NOTION_DB_ID)

        tasks = []

        for r in results["results"]:
            props = r.get("properties", {})

            # -------- TITLE (robust) --------
            title = "UNKNOWN TASK"
            task_prop = props.get("Task", {})

            # title format
            title_arr = task_prop.get("title", [])
            if title_arr:
                t = title_arr[0]
                title = (
                    t.get("plain_text")
                    or t.get("text", {}).get("content")
                    or title
                )

            # rich_text fallback
            elif task_prop.get("rich_text"):
                rt = task_prop["rich_text"]
                if rt:
                    title = rt[0].get("plain_text", title)

            # -------- STATUS --------
            status_obj = props.get("Status", {}).get("select")
            status = status_obj.get("name") if status_obj else ""

            print(f"[NOTION] {title} | {status}")

            tasks.append({
                "title": title,
                "status": status
            })

        print(f"[NOTION] TOTAL TASKS: {len(tasks)}")
        return tasks

    except Exception:
        print("💥 NOTION QUERY ERROR")
        traceback.print_exc()
        return []

# -------------------------
# PENDING FILTER (FIXED)
# -------------------------
def normalize(s):
    return "".join(c for c in str(s).lower() if c.isalnum())

def pending_tasks():
    tasks = get_tasks()
    return [t for t in tasks if "pending" in normalize(t.get("status"))]

def top_task():
    tasks = pending_tasks()
    return tasks[0]["title"] if tasks else None

# -------------------------
# SAVE TASK
# -------------------------
def save_task(task):
    try:
        notion.pages.create(
            parent={"database_id": NOTION_DB_ID},
            properties={
                "Task": {"title": [{"text": {"content": task}}]},
                "Status": {"select": {"name": "Pending"}},
            },
        )
    except Exception:
        print("💥 NOTION CREATE ERROR")
        traceback.print_exc()

# -------------------------
# MARK DONE
# -------------------------
def mark_done(task_name):
    try:
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

    except Exception:
        print("💥 NOTION UPDATE ERROR")
        traceback.print_exc()
        return False

# -------------------------
# BOT LOGIC
# -------------------------
def reply_logic(text):
    text = text.lower().strip()

    if text == "focus":
        task = top_task()
        return jesse(f"Do this right now → {task}") if task else jesse("No tasks. You're free.")

    if text == "today":
        tasks = pending_tasks()[:3]
        if not tasks:
            return jesse("Nothing on your plate.")
        return jesse("Top priorities:\n- " + "\n- ".join([t["title"] for t in tasks]))

    if text.startswith("add "):
        save_task(text[4:].strip())
        return jesse("Task added.")

    if text == "list":
        tasks = pending_tasks()
        if not tasks:
            return jesse("No pending jobs.")
        return jesse("Your backlog:\n- " + "\n- ".join([t["title"] for t in tasks]))

    return jesse(random.choice(["Noted.", "Alright.", "Got it.", "Say less.", "I'm tracking it."]))

# -------------------------
# HANDLER
# -------------------------
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        msg = update.message
        if not msg or not msg.text:
            return

        text = msg.text.strip()
        gif_key = "default"

        if text.lower().startswith("add "):
            save_task(text[4:].strip())
            gif_key = "add"
            reply = jesse("Task added.")

        elif text.lower().startswith("done "):
            ok = mark_done(text[5:].strip())
            gif_key = "done"
            reply = jesse("Task completed." if ok else "Couldn't find that task.")

        elif text.lower() == "focus":
            gif_key = "focus"
            reply = reply_logic(text)

        else:
            reply = reply_logic(text)

        await send_gif(update, gif_key)
        await msg.reply_text(reply)

    except Exception:
        print("[HANDLER CRASH]")
        traceback.print_exc()

# -------------------------
# MAIN
# -------------------------
def main():
    print("🚀 Starting bot...")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    print("🔥 Jesse OS RUNNING")
    app.run_polling()

if __name__ == "__main__":
    main()
