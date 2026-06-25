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


# -------------------------
# JESSE
# -------------------------
def jesse(text):
    return random.choice(["Yo. ", "Alright. ", "Bruh, ", "Listen. "]) + text + " yo."


# -------------------------
# GIF SENDER (RESTORED)
# -------------------------
async def send_gif(update: Update, key: str):
    try:
        if not update.message:
            return

        file_id = JESSE_GIFS.get(key) or random.choice(DEFAULT_GIFS)
        await update.message.reply_animation(animation=file_id)

    except Exception:
        print("[GIF ERROR]")
        traceback.print_exc()


# -------------------------
# NOTION FETCH (ROBUST)
# -------------------------
def get_tasks():
    try:
        results = notion.databases.query(database_id=NOTION_DB_ID)

        tasks = []

        for r in results.get("results", []):
            props = r.get("properties", {})

            # title
            title_prop = props.get("Task", {}).get("title", [])
            title = "UNKNOWN TASK"

            if title_prop:
                title = title_prop[0].get("plain_text", title)

            # status (Select)
            status_obj = props.get("Status", {}).get("select")
            status = (status_obj.get("name") if status_obj else "")
            status = status.strip().lower()

            print(f"FOUND → {title} | STATUS → {status}")

            tasks.append({"title": title, "status": status})

        print("TOTAL TASKS:", len(tasks))
        return tasks

    except Exception:
        print("💥 NOTION ERROR")
        traceback.print_exc()
        return []


# -------------------------
# FIXED FILTER (REALISTIC)
# -------------------------
PENDING_STATES = {"pending", "to do", "todo", "in progress"}

def pending_tasks():
    tasks = get_tasks()

    filtered = [
        t for t in tasks
        if (t.get("status") or "") in PENDING_STATES
    ]

    print("PENDING FOUND:", len(filtered))
    return filtered


def top_task():
    tasks = pending_tasks()
    return tasks[0]["title"] if tasks else None


# -------------------------
# SAVE
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
        traceback.print_exc()


# -------------------------
# DONE
# -------------------------
def mark_done(task_name):
    try:
        results = notion.databases.query(
            database_id=NOTION_DB_ID,
            filter={"property": "Task", "title": {"contains": task_name}}
        )

        if not results.get("results"):
            return False

        page_id = results["results"][0]["id"]

        notion.pages.update(
            page_id=page_id,
            properties={"Status": {"select": {"name": "Done"}}}
        )

        return True

    except Exception:
        traceback.print_exc()
        return False


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
        save_task(text[4:].strip())
        return jesse("Task added.")

    return jesse("Noted.")


# -------------------------
# HANDLER (FIXED GIF FLOW)
# -------------------------
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        msg = update.message
        if not msg or not msg.text:
            return

        text = msg.text.lower().strip()

        gif_key = "default"
        reply = reply_logic(text)

        if text.startswith("add "):
            gif_key = "add"
        elif text == "focus":
            gif_key = "focus"
        elif text.startswith("done "):
            gif_key = "done"

        await send_gif(update, gif_key)
        await msg.reply_text(reply)

    except Exception:
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
