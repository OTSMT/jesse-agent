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
# JESSE STYLE (UNCHANGED)
# -------------------------
def jesse(text):
    return random.choice(["Yo. ", "Alright. ", "Listen. ", "Bruh, "]) + text + " yo."

# -------------------------
# GIFS (SAFE)
# -------------------------
JESSE_GIFS = {
    "add": "CgACAgQAAxkBAANxaj0LFl0u4HHc0CpZWroUYFZ8loAAAtUCAAJVlQxTBkmzB2EPQCo8BA",
    "done": "CgACAgQAAxkBAANyaj0LJVuPaT_cfd4RvqIivMF4vdMAAv4CAAKzsAxTGIFPam3qjak8BA",
    "focus": "CgACAgQAAxkBAANzaj0LQ3LnyEwYQ_aw8-CtZsA07l4AAhwHAAJ2b0VQAAFnz-zlNdQgPAQ",
}

DEFAULT_GIF = "CgACAgQAAxkBAANwaj0LDR9fIlU9WkEigLOHE5sV2wMAAiQDAAIqpyxTGZ0lrfl2IpQ8BA"

async def send_gif(update: Update, key: str):
    try:
        gif = JESSE_GIFS.get(key)
        if gif:
            await update.message.reply_animation(animation=gif)
    except Exception as e:
        print("GIF ERROR:", e)

# -------------------------
# NOTION FETCH (DEBUG ENABLED)
# -------------------------
def get_tasks():
    try:
        res = notion.databases.query(database_id=NOTION_DB_ID)

        results = res.get("results", [])

        print("\n==== NOTION DEBUG ====")
        print("DB ID:", NOTION_DB_ID)
        print("TASK COUNT:", len(results))

        return results

    except Exception as e:
        print("QUERY ERROR:", e)
        traceback.print_exc()
        return []

# -------------------------
# SAFE PROPERTY PARSING
# -------------------------
def extract_title(page):
    try:
        props = page.get("properties", {})
        for v in props.values():
            if v.get("type") == "title":
                t = v.get("title", [])
                return t[0]["plain_text"] if t else "UNKNOWN"
    except:
        pass
    return "UNKNOWN"

def extract_status(page):
    try:
        props = page.get("properties", {})
        for v in props.values():

            if v.get("type") == "select":
                sel = v.get("select")
                if sel and sel.get("name"):
                    return sel["name"].strip().lower()

        # IMPORTANT FIX: treat missing status as pending
        return "pending"

    except:
        return "pending"

# -------------------------
# FILTER LOGIC (FIXED)
# -------------------------
def pending_tasks():
    tasks = get_tasks()

    result = []
    for t in tasks:
        status = extract_status(t)
        if status != "done":
            result.append(t)

    return result

def top_task():
    tasks = pending_tasks()
    return extract_title(tasks[0]) if tasks else None

# -------------------------
# ADD TASK
# -------------------------
def save_task(text):
    try:
        notion.pages.create(
            parent={"database_id": NOTION_DB_ID},
            properties={
                "Task": {"title": [{"text": {"content": text}}]},
                "Status": {"select": {"name": "Pending"}},
            },
        )
        print("ADDED:", text)
    except Exception as e:
        print("ADD ERROR:", e)
        traceback.print_exc()

# -------------------------
# DONE TASK
# -------------------------
def mark_done(name):
    try:
        tasks = get_tasks()

        for t in tasks:
            title = extract_title(t)

            if title.strip().lower() == name.strip().lower():
                notion.pages.update(
                    page_id=t["id"],
                    properties={
                        "Status": {"select": {"name": "Done"}}
                    },
                )
                print("DONE:", title)
                return True

        print("NOT FOUND:", name)
        return False

    except Exception as e:
        print("DONE ERROR:", e)
        traceback.print_exc()
        return False

# -------------------------
# BOT LOGIC
# -------------------------
def reply(text):
    text = text.lower().strip()

    if text == "list":
        tasks = pending_tasks()
        if not tasks:
            return jesse("No pending jobs.")
        return jesse("Tasks:\n- " + "\n- ".join(extract_title(t) for t in tasks))

    if text == "focus":
        task = top_task()
        return jesse(f"Do this → {task}") if task else jesse("No tasks.")

    if text.startswith("add "):
        save_task(text[4:])
        return jesse("Task added.")

    if text.startswith("done "):
        ok = mark_done(text[5:])
        return jesse("Done." if ok else "Not found.")

    return jesse("Noted.")

# -------------------------
# HANDLER (SAFE GIF FLOW)
# -------------------------
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = update.message.text.strip()

        response = reply(text)

        # GIF triggers
        try:
            if text.startswith("add "):
                await send_gif(update, "add")
            elif text.startswith("done "):
                await send_gif(update, "done")
            elif text == "focus":
                await send_gif(update, "focus")
        except Exception as e:
            print("GIF ERROR:", e)

        await update.message.reply_text(response)

    except Exception as e:
        print("HANDLER ERROR:", e)
        traceback.print_exc()

# -------------------------
# RUN
# -------------------------
def main():
    print("RUNNING BOT")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    app.run_polling()

if __name__ == "__main__":
    main()
