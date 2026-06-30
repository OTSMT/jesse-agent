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

        # Jesse 2.0
        "last_messages": [],
        "last_reply_time": None,
        "repeat_block": "",

        # Jesse 3.0
        "task_memory": {},
        "weekly_stats": {
            "adds": 0,
            "done": 0,
            "week_start": str(datetime.date.today()),
        },

        # 🔥 JESSE 3.5 ADDITIONS
        "task_emotions": {},          # task -> avoid/neutral/liked
        "task_fail_patterns": {},     # task -> fail count
        "weekly_history": [],
        "global_behavior_score": 0,
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
# 3.5 TASK INTELLIGENCE
# -------------------------
def set_task_emotion(task, state):
    MEMORY["task_emotions"][task] = state


def get_task_emotion(task):
    return MEMORY["task_emotions"].get(task, "neutral")


def update_fail_pattern(task, success):
    if task not in MEMORY["task_fail_patterns"]:
        MEMORY["task_fail_patterns"][task] = 0

    if not success:
        MEMORY["task_fail_patterns"][task] += 1


def failure_level(task):
    return MEMORY["task_fail_patterns"].get(task, 0)


def task_score(task):
    # higher = more ignored / avoided
    age = MEMORY["task_memory"].get(task, {}).get("mentions", 0)
    fails = failure_level(task)
    return age + (fails * 3)

# -------------------------
# BEHAVIOR SYSTEM
# -------------------------
def update_relationship():
    MEMORY["relationship"] += 1


def track_action(action):
    MEMORY["recent_actions"].append(action)
    if len(MEMORY["recent_actions"]) > 7:
        MEMORY["recent_actions"].pop(0)


def update_behavior_history():
    recent = MEMORY["recent_actions"]
    adds = recent.count("add")
    dones = recent.count("done")

    if adds == 0 and dones == 0:
        MEMORY["behavior_history"].append("idle")
    elif adds > dones:
        MEMORY["behavior_history"].append("overload")
    else:
        MEMORY["behavior_history"].append("productive")

    if len(MEMORY["behavior_history"]) > 25:
        MEMORY["behavior_history"].pop(0)


def arc_state_update():
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


def update_emotion():
    h = MEMORY["behavior_history"]
    if len(h) < 3:
        return

    stress = h[-10:].count("overload")
    calm = h[-10:].count("productive")

    MEMORY["emotion_state"] = (
        "stressed" if stress > calm else
        "calm" if calm > stress else
        "neutral"
    )


def personality():
    seed = (MEMORY["relationship"] + MEMORY["conversations"]) % 100
    MEMORY["personality_seed"] = seed

    if seed < 20:
        return "cold"
    elif seed < 50:
        return "neutral"
    elif seed < 80:
        return "warm"
    return "chaotic"

# -------------------------
# HUMAN LAYER
# -------------------------
def handle_human(text):
    t = text.lower().strip()
    p = personality()

    if t in ["hi", "hello", "yo", "hey"]:
        return random.choice({
            "cold": ["Yeah.", "What.", "Yo."],
            "warm": ["Yo man.", "Hey.", "Yeah what's up."],
            "chaotic": ["Yo… again?", "What now.", "Yeah yeah I’m here."]
        }.get(p, ["Yo.", "Yeah?", "What."]))

    if t in ["thanks", "thank you"]:
        return random.choice(["Yeah.", "No problem.", "We good."])

    if t in ["bye", "goodbye"]:
        return random.choice(["Later.", "Aight.", "Don’t disappear."])

    return None

# -------------------------
# SPEECH ENGINE (3.5)
# -------------------------
def messify(base, arc, emotion, rel):

    p = personality()

    text = random.choice({
        "cold": ["Yo", "Aight", ""],
        "neutral": ["Yo", "Yo…", "Alright"],
        "warm": ["Yo man", "Aight bro", "Yo"],
        "chaotic": ["Yo…", "Bro", "Yo yo", ""]
    }[p]) + " " + base

    if arc == "strict":
        text += " Focus."
    elif arc == "locked_in":
        text += " Keep going."

    if emotion == "stressed":
        text += " Slow down."

    # LONG TERM VOICE DRIFT
    if rel > 60 and random.random() < 0.2:
        text = "I’ve seen this pattern before. " + text

    if p == "chaotic":
        text += random.choice([" not gonna lie.", " idk.", " whatever."])

    return text.strip()

# -------------------------
# CORE REPLY
# -------------------------
def reply(text):

    MEMORY["conversations"] += 1
    track_action("other")

    if text.startswith("add"):
        task = text.replace("add", "", 1).strip()
        save_task(task)

        MEMORY["tasks_added"] += 1
        track_action("add")

        set_task_emotion(task, "neutral")
        return "Got it.", "task_added"

    if text.startswith("done"):
        task = text.replace("done", "", 1).strip()
        ok = mark_done(task)

        track_action("done")

        if ok:
            MEMORY["tasks_done"] += 1
            update_fail_pattern(task, True)
            return "Done.", "task_done"

        update_fail_pattern(task, False)
        return "Not found.", "default"

    if text == "focus":
        tasks = pending_tasks()
        if not tasks:
            return "Nothing left.", "default"

        t = extract_title(tasks[0])
        score = task_score(t)

        if score > 12:
            return f"You’ve been avoiding this for a while → {t}", "focus"
        elif score > 6:
            return f"This again… → {t}", "focus"

        return "Do this → " + t, "focus"

    if text == "list":
        tasks = pending_tasks()
        if not tasks:
            return "Nothing left.", "default"
        return "Here’s the board:\n- " + "\n- ".join(extract_title(t) for t in tasks), "default"

    return "Yo.", "default"

# -------------------------
# HANDLER
# -------------------------
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = update.message.text.lower().strip()

        update_relationship()
        update_behavior_history()
        arc_state_update()
        update_emotion()

        base, event = reply(text)

        final = messify(
            base,
            MEMORY["arc_state"],
            MEMORY["emotion_state"],
            MEMORY["relationship"]
        )

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
