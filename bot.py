import os
import random
import time
import json
import datetime
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

notion = Client(auth=NOTION_API_KEY)

# -------------------------
# GIF ENGINE (V2 - EMOTION POOLS)
# Replace placeholders with real Telegram file_ids
# -------------------------
JESSE_GIF_POOLS = {
    "add": {
        "chaos": ["gif_add_1", "gif_add_2"],
        "hustler": ["gif_add_3"],
        "disciplined": ["gif_add_4"],
        "machine": ["gif_add_5"],
    },

    "done": {
        "strict": ["gif_done_1"],
        "disappointed": ["gif_done_2"],
        "neutral": ["gif_done_3"],
        "supportive": ["gif_done_4"],
        "proud": ["gif_done_5"],
    },

    "focus": {
        "chaos": ["gif_focus_1"],
        "hustler": ["gif_focus_2"],
        "disciplined": ["gif_focus_3"],
        "machine": ["gif_focus_4"],
    }
}

def pick_gif(action, relationship, arc):
    pools = JESSE_GIF_POOLS.get(action)
    if not pools:
        return None

    category = relationship if action == "done" else arc

    gifs = pools.get(category)

    if not gifs:
        gifs = pools.get("neutral") or []
    if not gifs:
        gifs = [g for v in pools.values() for g in v]

    return random.choice(gifs) if gifs else None


async def send_gif(update: Update, action=None, relationship=None, arc=None):
    try:
        gif = pick_gif(action, relationship, arc)
        if not gif:
            return

        await update.get_bot().send_animation(
            chat_id=update.effective_chat.id,
            animation=gif
        )
    except:
        pass

# -------------------------
# MEMORY
# -------------------------
MEM_FILE = "jesse_memory.json"

def load_memory():
    try:
        with open(MEM_FILE, "r") as f:
            return json.load(f)
    except:
        return {
            "tasks_added": 0,
            "tasks_done": 0,
            "last_seen": time.time(),
            "streak": 0,
            "last_day": None,
            "weekly_added": 0,
            "weekly_done": 0,
            "week_start": time.time(),
            "trust": 5,
            "failures": 0,
            "ignore_map": {},
            "recent_performance": [],
        }

MEMORY = load_memory()

def save_memory():
    with open(MEM_FILE, "w") as f:
        json.dump(MEMORY, f)

# -------------------------
# STREAK / WEEK
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

def update_week():
    if time.time() - MEMORY["week_start"] > 7 * 24 * 3600:
        MEMORY["weekly_added"] = 0
        MEMORY["weekly_done"] = 0
        MEMORY["week_start"] = time.time()

def update_activity():
    now = time.time()

    if now - MEMORY["last_seen"] > 6 * 3600:
        MEMORY["streak"] = max(0, MEMORY["streak"] - 1)

    MEMORY["last_seen"] = now
    update_streak()
    update_week()

# -------------------------
# NOTION
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
# EMOTIONAL MEMORY
# -------------------------
def update_recent(success: bool):
    MEMORY["recent_performance"].append(1 if success else 0)
    if len(MEMORY["recent_performance"]) > 10:
        MEMORY["recent_performance"].pop(0)

def get_recent_score():
    if not MEMORY["recent_performance"]:
        return 0.5
    return sum(MEMORY["recent_performance"]) / len(MEMORY["recent_performance"])

def get_relationship():
    score = get_recent_score()
    trust = MEMORY["trust"]

    if score > 0.8 and trust >= 7:
        return "proud"
    if score > 0.6:
        return "supportive"
    if score > 0.4:
        return "neutral"
    if score > 0.2:
        return "disappointed"
    return "strict"

# -------------------------
# PERSONALITY
# -------------------------
def mood(task_count):
    if task_count == 0:
        return "calm"
    if task_count <= 2:
        return "focused"
    if task_count <= 5:
        return "busy"
    return "overloaded"

def arc():
    s = MEMORY["streak"]
    if s <= 1:
        return "chaos"
    if s <= 4:
        return "hustler"
    if s <= 9:
        return "disciplined"
    return "machine"

def jesse(text, task_count):
    rel = get_relationship()
    a = arc()
    m = mood(task_count)

    base = {
        "chaos": ["Yo… ", "Bro… "],
        "hustler": ["Yo. ", "Aight. "],
        "disciplined": ["Locked in. ", "Respect. "],
        "machine": ["No stopping. ", "Execution. "],
    }.get(a, ["Yo. "])

    relation_layer = {
        "proud": ["Proud of you. ", "This is clean. "],
        "supportive": ["Good work. ", "We steady. "],
        "neutral": [""],
        "disappointed": ["Hmm. ", "We slipping. "],
        "strict": ["Bro listen. ", "Fix this. "],
    }.get(rel, [""])

    suffix = {
        "calm": [".", " We good."],
        "focused": [" Stay sharp.", " Lock in."],
        "busy": [" Keep going.", " Don’t stop."],
        "overloaded": [" Fix this.", " Too much."],
    }.get(m, [""])

    return random.choice(base + relation_layer) + text + random.choice(suffix)

# -------------------------
# REPLY
# -------------------------
def reply(text):
    task_count = len(pending_tasks())
    t = text.lower().strip()

    if "add" in t:
        task = t.replace("add", "", 1).strip()
        save_task(task)
        MEMORY["tasks_added"] += 1
        MEMORY["weekly_added"] += 1
        update_recent(False)
        return jesse("Task added.", task_count), "add", True

    if "done" in t:
        task = t.replace("done", "", 1).strip()
        ok = mark_done(task)

        if ok:
            MEMORY["tasks_done"] += 1
            MEMORY["weekly_done"] += 1

        update_recent(ok)
        return jesse("Done." if ok else "Not found.", task_count), "done" if ok else None, ok

    if t == "focus":
        tasks = pending_tasks()
        best = tasks[0] if tasks else None
        return jesse("Do this → " + extract_title(best) if best else "No tasks.", task_count), "focus", True

    if t == "list":
        return jesse(
            "Tasks:\n- " + "\n- ".join(extract_title(x) for x in pending_tasks())
            if task_count else "No tasks.",
            task_count
        ), None, True

    return jesse("Noted.", task_count), None, True

# -------------------------
# HANDLER
# -------------------------
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        update_activity()

        text = update.message.text
        response, action, success = reply(text)

        save_memory()

        await update.message.reply_text(response)

        if action:
            await send_gif(
                update,
                action=action,
                relationship=get_relationship(),
                arc=arc()
            )

    except Exception as e:
        print("ERROR:", e)
        traceback.print_exc()

# -------------------------
# RUN
# -------------------------
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    app.run_polling()

if __name__ == "__main__":
    main()
