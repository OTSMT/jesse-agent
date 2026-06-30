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

        # 9.0 features kept
        "task_weights": {},
        "repeat_guard": "",
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
# WEIGHT SYSTEM (kept)
# -------------------------
def update_task_weight(title, success):
    if title not in MEMORY["task_weights"]:
        MEMORY["task_weights"][title] = 0

    if success:
        MEMORY["task_weights"][title] -= 0.5
    else:
        MEMORY["task_weights"][title] += 1


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
# GIF SYSTEM (FIXED + GUARANTEED)
# -------------------------
GIFS = {
    "task_added": [
        "CgACAgQAAxkBAAIFpGo_i6l-7y4q7oZeumVRjAMha46MAAJMBgACCpJFUc5OZtXsmw9OPAQ"
    ],
    "task_done": [
        "CgACAgQAAxkBAANvaj0LBnguOITXUPIWodCIx7BUCGsAArYDAAKCb51QTuahwuylJAk8BA"
    ],
    "focus": [
        "CgACAgQAAxkBAAIFpGo_i6l-7y4q7oZeumVRjAMha46MAAJMBgACCpJFUc5OZtXsmw9OPAQ"
    ],
    "default": [
        "CgACAgQAAxkBAANwaj0LDR9fIlU9WkEigLOHE5sV2wMAAiQDAAIqpyxTGZ0lrfl2IpQ8BA"
    ]
}


def resolve_event(event):
    if event in GIFS:
        return event
    return "default"


def get_gif(event):
    return random.choice(GIFS[resolve_event(event)])


async def send_gif(update: Update, context: ContextTypes.DEFAULT_TYPE, event: str):
    try:
        await context.bot.send_animation(
            chat_id=update.effective_chat.id,
            animation=get_gif(event)
        )
    except:
        pass

# -------------------------
# CORE REPLY (FIXED SIGNALING)
# -------------------------
def reply(text):

    MEMORY["conversations"] += 1

    if MEMORY.get("repeat_guard") == text:
        return "Yeah.", "default"
    MEMORY["repeat_guard"] = text

    tasks = pending_tasks()

    # IMPORTANT FIX: guaranteed event routing

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
        MEMORY["tasks_added"] += 1
        MEMORY["recent_actions"].append("add")
        update_task_weight(task, False)

        save_task(task)
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

        final = response

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
