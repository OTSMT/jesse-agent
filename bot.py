import os
import random
import datetime
import traceback
import json

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
# MEMORY
# -------------------------
MEMORY_PAGE_NAME = "JESSE_MEMORY"


def get_memory_page():
    try:
        pages = notion.databases.query(database_id=NOTION_DB_ID).get("results", [])
        for p in pages:
            props = p.get("properties", {})
            title = props.get("Task", {}).get("title", [])
            if title and title[0]["plain_text"].strip().upper() == MEMORY_PAGE_NAME:
                return p
    except:
        pass
    return None


def load_memory():
    page = get_memory_page()

    default = {
        "tasks_added": 0,
        "tasks_done": 0,
        "conversations": 0,

        "recent_actions": [],
        "behavior_history": [],

        "arc_state": "supportive",
        "emotion_state": "neutral",

        "relationship": 0,
        "weekly_stats": {"adds": 0, "done": 0},

        # 8.0 retained
        "pressure_map": {},
        "repeat_guard": "",
        "prediction": None,

        # 9.0 NEW
        "task_weights": {},
        "category_success": {},
        "focus_lock": None
    }

    if not page:
        return default

    try:
        props = page.get("properties", {})
        data = props.get("Data", {}).get("rich_text", [])
        if not data:
            return default

        raw = data[0]["plain_text"]
        return {**default, **json.loads(raw)}

    except:
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
                        {"text": {"content": json.dumps(mem)}}
                    ]
                }
            },
        )
    except:
        pass


MEMORY = load_memory()

# -------------------------
# TASK SYSTEM
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
        status = props.get("Status", {}).get("select")
        if status and status.get("name"):
            return status["name"].strip().lower()
    except:
        pass
    return "pending"


def pending_tasks():
    return [t for t in get_tasks() if extract_status(t) != "done"]

# -------------------------
# TASK WEIGHT SYSTEM (9.0 CORE)
# -------------------------
def task_weight(title, status):
    base = 1

    if title in MEMORY["task_weights"]:
        base += MEMORY["task_weights"][title]

    if status != "done":
        base += 1

    return base


def update_task_weight(title, success):
    if title not in MEMORY["task_weights"]:
        MEMORY["task_weights"][title] = 0

    if success:
        MEMORY["task_weights"][title] -= 0.5
    else:
        MEMORY["task_weights"][title] += 1

# -------------------------
# CATEGORY SYSTEM
# -------------------------
def detect_category(text):
    t = text.lower()
    if any(x in t for x in ["email", "invoice", "call"]):
        return "admin"
    if any(x in t for x in ["study", "read", "learn"]):
        return "learning"
    if any(x in t for x in ["work", "project"]):
        return "work"
    if any(x in t for x in ["gym", "run", "sleep"]):
        return "personal"
    return "unknown"


def category_pressure(cat):
    d = MEMORY["pressure_map"].get(cat, {"hit": 0, "miss": 0})
    return d["miss"] / (d["hit"] + d["miss"] + 1)

# -------------------------
# BEHAVIOR CORE
# -------------------------
def update_behavior():
    r = MEMORY["recent_actions"]

    adds = r.count("add")
    dones = r.count("done")

    if adds == 0 and dones == 0:
        MEMORY["behavior_history"].append("idle")
    elif adds > dones:
        MEMORY["behavior_history"].append("overload")
    else:
        MEMORY["behavior_history"].append("productive")

    if len(MEMORY["behavior_history"]) > 30:
        MEMORY["behavior_history"].pop(0)


def arc_state():
    h = MEMORY["behavior_history"]
    if len(h) < 5:
        MEMORY["arc_state"] = "supportive"
        return

    recent = h[-5:]
    if recent.count("overload") >= 3:
        MEMORY["arc_state"] = "strict"
    elif recent.count("productive") >= 3:
        MEMORY["arc_state"] = "locked_in"
    else:
        MEMORY["arc_state"] = "supportive"


def emotion():
    h = MEMORY["behavior_history"][-10:]
    MEMORY["emotion_state"] = (
        "stressed" if h.count("overload") > h.count("productive")
        else "calm" if h.count("productive") > h.count("overload")
        else "neutral"
    )

# -------------------------
# SMART FOCUS (9.0 CORE)
# -------------------------
def pick_focus_task(tasks):
    if not tasks:
        return None

    scored = []
    for t in tasks:
        title = extract_title(t)
        weight = MEMORY["task_weights"].get(title, 0)
        scored.append((weight, title))

    scored.sort(reverse=True)
    return scored[0][1]

# -------------------------
# HUMAN LAYER
# -------------------------
def handle_human(text):
    t = text.lower().strip()

    if t in ["hi", "hello", "yo", "hey"]:
        return random.choice(["Yo.", "Yeah.", "What."])

    if t in ["thanks", "thank you"]:
        return "Yeah."

    if t in ["bye", "goodbye"]:
        return "Later."

    return None

# -------------------------
# GIF SYSTEM (SAFE LOCK)
# -------------------------
GIFS = {
    "task_added": ["CgACAgQAAxkBAAIFpGo_i6l-7y4q7oZeumVRjAMha46MAAJMBgACCpJFUc5OZtXsmw9OPAQ"],
    "task_done": ["CgACAgQAAxkBAANvaj0LBnguOITXUPIWodCIx7BUCGsAArYDAAKCb51QTuahwuylJAk8BA"],
    "focus": ["CgACAgQAAxkBAAIFpGo_i6l-7y4q7oZeumVRjAMha46MAAJMBgACCpJFUc5OZtXsmw9OPAQ"],
    "default": ["CgACAgQAAxkBAANwaj0LDR9fIlU9WkEigLOHE5sV2wMAAiQDAAIqpyxTGZ0lrfl2IpQ8BA"]
}


def get_gif(event):
    return random.choice(GIFS.get(event or "default", GIFS["default"]))


async def send_gif(update: Update, context: ContextTypes.DEFAULT_TYPE, event: str):
    try:
        await context.bot.send_animation(
            chat_id=update.effective_chat.id,
            animation=get_gif(event)
        )
    except:
        pass

# -------------------------
# SPEECH ENGINE
# -------------------------
def personality():
    seed = (MEMORY["relationship"] + MEMORY["conversations"]) % 100
    return (
        "cold" if seed < 20 else
        "neutral" if seed < 50 else
        "warm" if seed < 80 else
        "chaotic"
    )


JESSE = {
    "cold": ["Yeah.", "What.", "Alright."],
    "neutral": ["Yo.", "Alright, listen.", "Yeah I got you."],
    "warm": ["Yo man.", "Aight, I hear you.", "Let’s go."],
    "chaotic": ["Yo… again?", "Bro what now.", "Aight aight."]
}


def messify(base, arc, emotion, rel):
    p = personality()

    text = random.choice(JESSE[p]) + " " + base

    if arc == "strict":
        text += " Focus."
    elif arc == "locked_in":
        text += " Keep going."

    if emotion == "stressed":
        text += " Slow down."

    if rel > 60 and random.random() < 0.2:
        text = "Still here? " + text

    return text.strip()

# -------------------------
# CORE REPLY
# -------------------------
def reply(text):

    MEMORY["conversations"] += 1

    if MEMORY.get("repeat_guard") == text:
        return "Yeah.", "default"
    MEMORY["repeat_guard"] = text

    tasks = pending_tasks()

    if text == "list":
        if not tasks:
            return "Nothing left.", "default"
        return "Here’s the board:\n- " + "\n- ".join(extract_title(t) for t in tasks), "default"

    if text == "focus":
        t = pick_focus_task(tasks)
        if not t:
            return "Nothing left.", "default"
        return "Do this → " + t, "focus"

    if text.startswith("add"):
        task = text.replace("add", "", 1).strip()
        save_task(task)
        MEMORY["tasks_added"] += 1
        MEMORY["recent_actions"].append("add")
        update_task_weight(task, False)
        return "Got it.", "task_added"

    if text.startswith("done"):
        task = text.replace("done", "", 1).strip()
        ok = mark_done(task)
        MEMORY["recent_actions"].append("done")

        if ok:
            MEMORY["tasks_done"] += 1
            update_task_weight(task, True)
            return "Done.", "task_done"

        update_task_weight(task, False)
        return "Not found.", "default"

    return "Yo.", "default"

# -------------------------
# HANDLER
# -------------------------
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = update.message.text.lower().strip()

        MEMORY["relationship"] += 1

        update_behavior()
        arc_state()
        emotion()

        response, event = reply(text)

        final = messify(
            response,
            MEMORY["arc_state"],
            MEMORY["emotion_state"],
            MEMORY["relationship"]
        )

        save_memory(MEMORY)

        await update.message.reply_text(final)
        await send_gif(update, context, event)

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
