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
# GIFS (UNCHANGED IDS)
# -------------------------
JESSE_GIFS = {
    "add": "CgACAgQAAxkBAANxaj0LFl0u4HHc0CpZWroUYFZ8loAAAtUCAAJVlQxTBkmzB2EPQCo8BA",
    "done": "CgACAgQAAxkBAANyaj0LJVuPaT_cfd4RvqIivMF4vdMAAv4CAAKzsAxTGIFPam3qjak8BA",
    "focus": "CgACAgQAAxkBAANzaj0LQ3LnyEwYQ_aw8-CtZsA07l4AAhwHAAJ2b0VQAAFnz-zlNdQgPAQ",
}

# -------------------------
# 🔥 DEBUG GIF SYSTEM (FULL VISIBILITY)
# -------------------------
async def send_gif(update: Update, key: str):
    try:
        print("\n===== GIF DEBUG START =====")
        print("KEY:", key)

        if not update:
            print("UPDATE IS NONE")
            return

        if not update.effective_chat:
            print("NO EFFECTIVE CHAT")
            return

        bot = update.get_bot()
        chat_id = update.effective_chat.id

        print("CHAT ID:", chat_id)

        gif = JESSE_GIFS.get(key)

        print("GIF FILE_ID:", gif)

        if not gif:
            print("NO GIF FOUND FOR KEY")
            return

        print("SENDING GIF NOW...")

        result = await bot.send_animation(
            chat_id=chat_id,
            animation=gif
        )

        print("GIF SENT SUCCESSFULLY")
        print("RESPONSE TYPE:", type(result))
        print("HAS ANIMATION:", hasattr(result, "animation"))

        if result and result.animation:
            print("ANIMATION FILE_ID RETURNED:", result.animation.file_id)

        print("===== GIF DEBUG END =====\n")

    except Exception as e:
        print("🔥 GIF FAILED HARD:", repr(e))
        traceback.print_exc()

# -------------------------
# NOTION (UNCHANGED)
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

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = update.message.text.strip()
        response = reply(text)

        print("\n=== MESSAGE RECEIVED ===")
        print("TEXT:", text)

        # GIF triggers (DEBUG MODE)
        if text.startswith("add "):
            await send_gif(update, "add")
        elif text.startswith("done "):
            await send_gif(update, "done")
        elif text == "focus":
            await send_gif(update, "focus")

        await update.message.reply_text(response)

    except Exception as e:
        print("HANDLER ERROR:", e)
        traceback.print_exc()

def main():
    print("RUNNING BOT")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    app.run_polling()

if __name__ == "__main__":
    main()
