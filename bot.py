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
        "personality_seed": 0,

        "weekly_stats": {"adds": 0, "done": 0},

        "task_categories": {},
        "avoidance_index": 0,
        "consistency_score": 0,

        # 7.0 ADDITIONS
        "last_outputs": [],
        "pressure_map": {},
        "habit_prediction": {},
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
# CATEGORY + PRESSURE SYSTEM
# -------------------------
def detect_category(text):
    t = text.lower()
    if any(x in t for x in ["email", "form", "invoice"]):
        return "admin"
    if any(x in t for x in ["study", "learn", "read"]):
        return "learning"
    if any(x in t for x in ["work", "project"]):
        return "work"
    if any(x in t for x in ["gym", "run", "sleep"]):
        return "personal"
    return "unknown"


def update_pressure(task, success):
    cat = detect_category(task)
    if cat not in MEMORY["pressure_map"]:
        MEMORY["pressure_map"][cat] = {"miss": 0, "hit": 0}

    if success:
        MEMORY["pressure_map"][cat]["hit"] += 1
    else:
        MEMORY["pressure_map"][cat]["miss"] += 1


def category_pressure(cat):
    d = MEMORY["pressure_map"].get(cat, {"hit": 0, "miss": 0})
    return d["miss"] / (d["hit"] + d["miss"] + 1)


def overall_pressure():
    total_miss = sum(v["miss"] for v in MEMORY["pressure_map"].values())
    total_hit = sum(v["hit"] for v in MEMORY["pressure_map"].values())
    return total_miss / (total_hit + 1)

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
# REPETITION GUARD (7.0 CORE)
# -------------------------
def repeat_guard(text):
    if text == MEMORY["repeat_guard"]:
        return True
    MEMORY["repeat_guard"] = text
    return False


def push_output(text):
    MEMORY["last_outputs"].append(text)
    if len(MEMORY["last_outputs"]) > 6:
        MEMORY["last_outputs"].pop(0)

# -------------------------
# PERSONALITY
# -------------------------
def personality():
    seed = (MEMORY["relationship"] + MEMORY["conversations"]) % 100
    if seed < 20:
        return "cold"
    if seed < 50:
        return "neutral"
    if seed < 80:
        return "warm"
    return "chaotic"

# -------------------------
# JESSE VOICE ENGINE 7.0 (HEAVY DIALOG VARIETY)
# -------------------------
JESSE_LINES = {
    "cold": [
        "Yeah.",
        "What.",
        "Alright.",
        "…yeah."
    ],
    "neutral": [
        "Yo.",
        "Alright, listen.",
        "Yeah I got you.",
        "Hmm."
    ],
    "warm": [
        "Yo man.",
        "Aight, I hear you.",
        "Yeah bro, okay.",
        "Let’s go."
    ],
    "chaotic": [
        "Yo… again?",
        "Bro what now.",
        "Aight aight I’m here.",
        "Yeah yeah yeah."
    ]
}


def jesse_prefix():
    p = personality()
    return random.choice(JESSE_LINES[p])

# -------------------------
# SPEECH ENGINE
# -------------------------
def messify(base, arc, emotion, rel):

    p = personality()
    pressure = overall_pressure()

    if pressure > 0.75:
        base = "You’re stacking too much again. " + base

    text = jesse_prefix() + " " + base

    # ARC BEHAVIOR
    if arc == "strict":
        text += " Focus."
    elif arc == "locked_in":
        text += " Keep going."

    # EMOTION LAYER
    if emotion == "stressed":
        text += " Slow down."
    elif emotion == "calm" and random.random() < 0.2:
        text += " That’s fine."

    # RELATIONSHIP LAYER
    if rel > 60 and random.random() < 0.25:
        text = "You again. " + text

    # PRESSURE PERSONALITY SHIFT
    if pressure > 0.8:
        text += " I’m not saying it twice."

    # VARIATION ENDINGS (IMPORTANT FOR NON-REPETITION)
    endings = ["", ".", "...", " yeah.", " man.", " alright."]
    text += random.choice(endings)

    return text.strip()

# -------------------------
# CORE REPLY
# -------------------------
def reply(text):

    MEMORY["conversations"] += 1

    if repeat_guard(text):
        return "Yeah.", "default"

    if text == "list":
        tasks = pending_tasks()
        if not tasks:
            return "Nothing left.", "default"
        return "Here’s the board:\n- " + "\n- ".join(extract_title(t) for t in tasks), "default"

    if text == "focus":
        tasks = pending_tasks()
        if not tasks:
            return "Nothing left.", "default"
        return "Do this → " + extract_title(tasks[0]), "default"

    if text.startswith("add"):
        task = text.replace("add", "", 1).strip()
        save_task(task)

        MEMORY["tasks_added"] += 1
        MEMORY["weekly_stats"]["adds"] += 1

        MEMORY["recent_actions"].append("add")
        update_pressure(task, True)

        return "Got it.", "task_added"

    if text.startswith("done"):
        task = text.replace("done", "", 1).strip()
        ok = mark_done(task)

        MEMORY["recent_actions"].append("done")

        if ok:
            MEMORY["tasks_done"] += 1
            MEMORY["weekly_stats"]["done"] += 1
            update_pressure(task, True)
            return "Done.", "task_done"

        update_pressure(task, False)
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

        push_output(final)
        save_memory(MEMORY)

        await update.message.reply_text(final)

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
