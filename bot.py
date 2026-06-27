import os
import random
import asyncio
import datetime
import traceback

from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters
from notion_client import Client

print("JESSE BOT STARTED")

# -------------------------
# ENV
# -------------------------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
NOTION_DB_ID = os.getenv("NOTION_DB_ID")

notion = Client(auth=NOTION_API_KEY)

# -------------------------
# GIFS (MOOD + EVENT)
# -------------------------
GIFS = {
    "add": {
        "calm": ["CgACAgQAAxkBAANxaj0LFl0u4HHc0CpZWroUYFZ8loAAAtUCAAJVlQxTBkmzB2EPQCo8BA"],
        "focused": ["CgACAgQAAxkBAANxaj0LFl0u4HHc0CpZWroUYFZ8loAAAtUCAAJVlQxTBkmzB2EPQCo8BA"],
        "overloaded": ["CgACAgQAAxkBAANxaj0LFl0u4HHc0CpZWroUYFZ8loAAAtUCAAJVlQxTBkmzB2EPQCo8BA"],
        "empty": ["CgACAgQAAxkBAANxaj0LFl0u4HHc0CpZWroUYFZ8loAAAtUCAAJVlQxTBkmzB2EPQCo8BA"]
    },
    "done": {
        "calm": ["CgACAgQAAxkBAANyaj0LJVuPaT_cfd4RvqIivMF4vdMAAv4CAAKzsAxTGIFPam3qjak8BA"],
        "focused": ["CgACAgQAAxkBAANyaj0LJVuPaT_cfd4RvqIivMF4vdMAAv4CAAKzsAxTGIFPam3qjak8BA"],
        "overloaded": ["CgACAgQAAxkBAANyaj0LJVuPaT_cfd4RvqIivMF4vdMAAv4CAAKzsAxTGIFPam3qjak8BA"],
        "empty": ["CgACAgQAAxkBAANyaj0LJVuPaT_cfd4RvqIivMF4vdMAAv4CAAKzsAxTGIFPam3qjak8BA"]
    },
    "focus": {
        "calm": ["CgACAgQAAxkBAANzaj0LQ3LnyEwYQ_aw8-CtZsA07l4AAhwHAAJ2b0VQAAFnz-zlNdQgPAQ"],
        "focused": ["CgACAgQAAxkBAANzaj0LQ3LnyEwYQ_aw8-CtZsA07l4AAhwHAAJ2b0VQAAFnz-zlNdQgPAQ"],
        "overloaded": ["CgACAgQAAxkBAANzaj0LQ3LnyEwYQ_aw8-CtZsA07l4AAhwHAAJ2b0VQAAFnz-zlNdQgPAQ"],
        "empty": []
    },
    "empty": {
        "calm": ["CgACAgQAAxkBAANyaj0LJVuPaT_cfd4RvqIivMF4vdMAAv4CAAKzsAxTGIFPam3qjak8BA"],
        "focused": ["CgACAgQAAxkBAANyaj0LJVuPaT_cfd4RvqIivMF4vdMAAv4CAAKzsAxTGIFPam3qjak8BA"],
        "overloaded": ["CgACAgQAAxkBAANyaj0LJVuPaT_cfd4RvqIivMF4vdMAAv4CAAKzsAxTGIFPam3qjak8BA"],
        "empty": ["CgACAgQAAxkBAANyaj0LJVuPaT_cfd4RvqIivMF4vdMAAv4CAAKzsAxTGIFPam3qjak8BA"]
    }
}

# -------------------------
# NOTION TASKS
# -------------------------
def get_tasks():
    try:
        return notion.databases.query(database_id=NOTION_DB_ID).get("results", [])
    except:
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
                if sel:
                    return sel["name"].lower()
        return "pending"
    except:
        return "pending"

def pending_tasks():
    return [t for t in get_tasks() if extract_status(t) != "done"]

def save_task(text):
    notion.pages.create(
        parent={"database_id": NOTION_DB_ID},
        properties={
            "Task": {"title": [{"text": {"content": text}}]},
            "Status": {"select": {"name": "Pending"}},
        },
    )

def mark_done(name):
    for t in get_tasks():
        if extract_title(t).strip().lower() == name.strip().lower():
            notion.pages.update(
                page_id=t["id"],
                properties={"Status": {"select": {"name": "Done"}}},
            )
            return True
    return False

# -------------------------
# MEMORY
# -------------------------
MEMORY_PAGE_NAME = "JESSE_MEMORY"

def get_memory_page():
    try:
        pages = notion.databases.query(database_id=NOTION_DB_ID).get("results", [])
        for p in pages:
            if extract_title(p).strip().upper() == MEMORY_PAGE_NAME:
                return p
    except:
        pass
    return None

def load_memory():
    page = get_memory_page()

    default = {
        "tasks_added": 0,
        "tasks_done": 0,
        "streak": 0,
        "last_day": None,
        "conversations": 0,
        "last_recap_date": None
    }

    if not page:
        return default

    try:
        props = page.get("properties", {})
        data = props.get("Data", {}).get("rich_text", [])
        if data:
            return {**default, **eval(data[0]["plain_text"])}
    except:
        pass

    return default

def save_memory(mem):
    page = get_memory_page()
    if not page:
        return

    try:
        notion.pages.update(
            page_id=page["id"],
            properties={
                "Data": {
                    "rich_text": [
                        {"text": {"content": str(mem)}}
                    ]
                }
            },
        )
    except:
        pass

MEMORY = load_memory()

# -------------------------
# STREAK
# -------------------------
def update_streak():
    today = datetime.date.today().isoformat()

    if MEMORY["last_day"] != today:
        yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()

        if MEMORY["last_day"] == yesterday:
            MEMORY["streak"] += 1
        else:
            MEMORY["streak"] = 1

        MEMORY["last_day"] = today

# -------------------------
# MOOD
# -------------------------
def mood(task_count):
    if task_count == 0:
        return "empty"
    if task_count <= 2:
        return "calm"
    if task_count <= 5:
        return "focused"
    return "overloaded"

# -------------------------
# JESSE TEXT ENGINE
# -------------------------
def jesse(event, task_count):
    update_streak()

    moods = {
        "calm": ["Yo. ", "Alright. ", "Aight. "],
        "focused": ["Lock in. ", "Yo. ", "Alright listen. "],
        "overloaded": ["Yo... ", "Bro... ", "This is a lot. "],
        "empty": ["... ", "Yo. ", "Damn. "]
    }

    lines = {
        "task_added": ["Added it.", "Boom. Mission added.", "Got it.", "Hell yeah."],
        "task_done": ["Hell yeah.", "Done.", "Off the board.", "Nice."],
        "not_found": ["Yo... not here.", "Nah.", "You sure?"],
        "list": ["Here's the board:", "Current missions:", "Alright:"],
        "empty": ["Nothing left.", "Board's clean.", "We’re done."],
        "focus": ["Do this → ", "Focus → ", "Only this → "]
    }

    m = mood(task_count)

    base = random.choice(moods[m])
    text = random.choice(lines.get(event, ["Yo."]))

    suffixes = ["", " yo.", " bitch.", " let's go.", " keep moving."]
    response = base + text + random.choice(suffixes)

    if random.random() < 0.03:
        response += "\n\nYeah. Science."

    return response

# -------------------------
# GIF ENGINE (FIXED + MOOD AWARE)
# -------------------------
def get_gif(event, task_count):
    if task_count == 0:
        m = "empty"
    elif task_count <= 2:
        m = "calm"
    elif task_count <= 5:
        m = "focused"
    else:
        m = "overloaded"

    pool = GIFS.get(event, {}).get(m, [])

    if not pool:
        return None

    return random.choice(pool)

async def send_gif(update: Update, event: str, task_count: int):
    try:
        gif = get_gif(event, task_count)

        if not gif:
            return

        await update.get_bot().send_animation(
            chat_id=update.effective_chat.id,
            animation=gif
        )
    except:
        pass

# -------------------------
# CORE LOGIC
# -------------------------
def reply(text):
    task_count = len(pending_tasks())
    MEMORY["conversations"] += 1

    if text == "list":
        tasks = pending_tasks()
        if not tasks:
            return jesse("empty", task_count), "empty"

        body = "\n- ".join(extract_title(t) for t in tasks)
        return jesse("list", task_count) + "\n- " + body, "list"

    if text == "focus":
        tasks = pending_tasks()
        if not tasks:
            return jesse("empty", task_count), "empty"
        return jesse("focus", task_count) + extract_title(tasks[0]), "focus"

    if text.startswith("add"):
        task = text.replace("add", "", 1).strip()
        save_task(task)
        MEMORY["tasks_added"] += 1
        return jesse("task_added", task_count), "add"

    if text.startswith("done"):
        task = text.replace("done", "", 1).strip()
        ok = mark_done(task)
        if ok:
            MEMORY["tasks_done"] += 1
            return jesse("task_done", task_count), "done"
        return jesse("not_found", task_count), "default"

    return jesse("list", task_count), "default"

# -------------------------
# DAILY RECAP
# -------------------------
async def send_daily_recap(bot):
    global MEMORY

    while True:
        try:
            today = datetime.date.today().isoformat()

            if MEMORY.get("last_recap_date") != today:
                task_count = len(pending_tasks())
                streak = MEMORY.get("streak", 0)

                if task_count == 0:
                    msg = f"Yo.\nBoard is clean.\nStreak: {streak}\nHell yeah, bitch."
                elif task_count <= 3:
                    msg = f"Yo.\nLooking good.\nPending: {task_count}\nStreak: {streak}"
                else:
                    msg = f"Yo...\nWe’re behind.\nPending: {task_count}\nStreak: {streak}"

                await bot.send_message(chat_id=YOUR_CHAT_ID, text=msg)

                MEMORY["last_recap_date"] = today
                save_memory(MEMORY)

        except:
            pass

        await asyncio.sleep(3600)

# -------------------------
# TELEGRAM HANDLER
# -------------------------
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = update.message.text.lower().strip()

        response, event = reply(text)

        save_memory(MEMORY)

        await update.message.reply_text(response)
        await send_gif(update, event, len(pending_tasks()))

    except Exception as e:
        print("ERROR:", e)
        traceback.print_exc()

# -------------------------
# RUN
# -------------------------
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

    asyncio.get_event_loop().create_task(send_daily_recap(app.bot))

    app.run_polling()

if __name__ == "__main__":
    main()
