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
# GIFS (UNCHANGED)
# -------------------------
JESSE_GIFS = {
    "add": "CgACAgQAAxkBAANxaj0LFl0u4HHc0CpZWroUYFZ8loAAAtUCAAJVlQxTBkmzB2EPQCo8BA",
    "done": "CgACAgQAAxkBAANyaj0LJVuPaT_cfd4RvqIivMF4vdMAAv4CAAKzsAxTGIFPam3qjak8BA",
    "focus": "CgACAgQAAxkBAANzaj0LQ3LnyEwYQ_aw8-CtZsA07l4AAhwHAAJ2b0VQAAFnz-zlNdQgPAQ",
}

# -------------------------
# JESSE MOOD ENGINE (NEW)
# -------------------------
def get_mood(task_count: int):
    if task_count == 0:
        return "calm"
    elif task_count <= 2:
        return "focused"
    elif task_count <= 5:
        return "busy"
    else:
        return "overloaded"

def mood_prefix(mood):
    if mood == "calm":
        return ["Yo. ", "Alright. ", "Nice and chill. "]

    if mood == "focused":
        return ["Yo. ", "Lock in. ", "Alright listen. "]

    if mood == "busy":
        return ["Yo. ", "We got work. ", "Alright this is stacking. "]

    if mood == "overloaded":
        return ["Yo!! ", "Bro this is a lot. ", "We drowning here. "]

    return ["Yo. "]

def mood_suffix(mood):
    if mood == "calm":
        return [" yo.", "", " we good."]
    if mood == "focused":
        return [" yo.", " stay sharp.", " you got this."]
    if mood == "busy":
        return [" yo.", " keep going.", " we moving."]
    if mood == "overloaded":
        return [" yo!", " too much man.", " we need cleanup."]
    return [" yo."]

# -------------------------
# CORE JESSE FUNCTION (UPDATED ONLY FEELING)
# -------------------------
def jesse(text, task_count=0):
    mood = get_mood(task_count)

    return (
        random.choice(mood_prefix(mood))
        + text
        + random.choice(mood_suffix(mood))
    )

# -------------------------
# NOTION
# -------------------------
def get_tasks():
    try:
        res = notion.databases.query(database_id=NOTION_DB_ID)
        results = res.get("results", [])

        print("\n==== NOTION DEBUG ====")
        print("TASK COUNT:", len(results))

        return results

    except Exception as e:
        print("QUERY ERROR:", e)
        traceback.print_exc()
        return []

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
        return "pending"
    except:
        return "pending"

def pending_tasks():
    tasks = get_tasks()
    return [t for t in tasks if extract_status(t) != "done"]

def top_task():
    tasks = pending_tasks()
    return extract_title(tasks[0]) if tasks else None

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
# BOT LOGIC (UNCHANGED)
# -------------------------
def reply(text):
    text = text.lower().strip()

    if text == "list":
        tasks = pending_tasks()
        if not tasks:
            return jesse("No pending jobs.", len(tasks))
        return jesse(
            "Tasks:\n- " + "\n- ".join(extract_title(t) for t in tasks),
            len(tasks)
        )

    if text == "focus":
        task = top_task()
        return jesse(f"Do this → {task}", len(pending_tasks())) if task else jesse("No tasks.", 0)

    if text.startswith("add"):
        save_task(text.replace("add", "", 1).strip())
        return jesse("Task added.", len(pending_tasks()) + 1)

    if text.startswith("done"):
        ok = mark_done(text.replace("done", "", 1).strip())
        return jesse("Done." if ok else "Not found.", len(pending_tasks()))

    return jesse("Noted.", len(pending_tasks()))

# -------------------------
# GIF SYSTEM (UNCHANGED)
# -------------------------
async def send_gif(update: Update, key: str):
    try:
        if not update or not update.effective_chat:
            return

        bot = update.get_bot()
        chat_id = update.effective_chat.id

        gif = JESSE_GIFS.get(key)

        if gif:
            await bot.send_animation(chat_id=chat_id, animation=gif)

    except Exception as e:
        print("GIF ERROR:", repr(e))
        traceback.print_exc()

# -------------------------
# HANDLER (UNCHANGED)
# -------------------------
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = update.message.text

        if not text:
            return

        normalized = text.strip().lower()

        print("\n=== MESSAGE RECEIVED ===")
        print("RAW:", text)
        print("NORMALIZED:", normalized)

        response = reply(normalized)

        await update.message.reply_text(response)
        await send_gif(update, "focus")

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
