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
# JESSE STYLE
# -------------------------
def jesse(text):
    return random.choice(["Yo. ", "Alright. ", "Bruh, ", "Listen. "]) + text + " yo."


# -------------------------
# GIF SENDER
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
# 🔥 NOTION DEBUG + SAFE PARSER
# -------------------------
def get_tasks():
    try:
        print("\n================ NOTION DEBUG ================")
        print("DB ID:", NOTION_DB_ID)

        results = notion.databases.query(database_id=NOTION_DB_ID)

        items = results.get("results", [])

        print("RAW RESULT COUNT:", len(items))

        if items:
            print("\nSAMPLE ITEM STRUCTURE:")
            print(items[0])

        tasks = []

        for r in items:
            props = r.get("properties", {})

            # --- TITLE DETECTION (robust) ---
            title = "UNKNOWN TASK"

            for key in ["Task", "Name", "Title"]:
                if key in props:
                    title_prop = props[key].get("title", [])
                    if title_prop:
                        title = title_prop[0].get("plain_text", title)
                        break

            # --- STATUS DETECTION ---
            status = ""
            if "Status" in props:
                status_obj = props["Status"].get("select")
                if status_obj:
                    status = status_obj.get("name", "")

            print(f"TASK → {title} | STATUS → {status}")

            tasks.append({
                "title": title,
                "status": status.strip().lower()
            })

        print("=============== END NOTION DEBUG ===============\n")

        return tasks

    except Exception:
        print("💥 NOTION QUERY ERROR")
        traceback.print_exc()
        return []


# -------------------------
# TASK LIST (NO FILTER - DEBUG MODE)
# -------------------------
def pending_tasks():
    tasks = get_tasks()

    print("TASKS SENT TO BOT:")
    print(tasks)

    return tasks


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
        traceback.print_exc()


# -------------------------
# MARK DONE
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

    if text == "list":
        tasks = pending_tasks()

        if not tasks:
            return jesse("No tasks found in Notion.")

        return jesse("Tasks:\n- " + "\n- ".join(t["title"] for t in tasks))

    return jesse("Noted.")


# -------------------------
# HANDLER
# -------------------------
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        msg = update.message
        if not msg or not msg.text:
            return

        reply = reply_logic(msg.text)

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
