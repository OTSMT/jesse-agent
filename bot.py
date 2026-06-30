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

        "weekly_stats": {
            "adds": 0,
            "done": 0,
            "week_start": str(datetime.date.today()),
        },

        "weekly_history": [],
        "daily_history": [],

        "task_fail_patterns": {},

        # 5.0 CORE ADDITIONS
        "identity_trend": [],
        "daily_state": "neutral",
        "prediction_memory": {},
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
            properties={"Data": {"rich_text": [{"text": {"content": json.dumps(mem)}}]}}
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
# DAILY SYSTEM (5.0 CORE)
# -------------------------
def update_daily_state():
    today = str(datetime.date.today())

    if MEMORY.get("last_day") != today:
        if MEMORY.get("last_day"):
            MEMORY["daily_history"].append(MEMORY.get("daily_state", "neutral"))

        MEMORY["last_day"] = today
        MEMORY["daily_state"] = "neutral"

    h = MEMORY["behavior_history"][-10:]

    adds = h.count("overload")
    done = h.count("productive")

    if adds > done:
        MEMORY["daily_state"] = "overload"
    elif done > adds:
        MEMORY["daily_state"] = "productive"
    else:
        MEMORY["daily_state"] = "neutral"

# -------------------------
# IDENTITY ENGINE (5.0)
# -------------------------
def compute_identity():
    w = MEMORY["weekly_stats"]
    ratio = w["done"] / (w["adds"] + 1)

    if ratio > 0.8:
        identity = "grinder"
    elif w["adds"] > 15 and w["done"] < 5:
        identity = "procrastinator"
    elif len(MEMORY["weekly_history"]) > 2 and MEMORY["weekly_history"][-1]["adds"] > MEMORY["weekly_history"][-1]["done"]:
        identity = "unstable"
    else:
        identity = "planner"

    MEMORY["identity"] = identity
    MEMORY["identity_trend"].append(identity)

    if len(MEMORY["identity_trend"]) > 20:
        MEMORY["identity_trend"].pop(0)

# -------------------------
# PREDICTION ENGINE (LIGHTWEIGHT)
# -------------------------
def predict_task(task):
    fails = MEMORY["task_fail_patterns"].get(task, 0)
    base = 0.5

    if fails > 3:
        base -= 0.3
    if MEMORY["identity"] == "procrastinator":
        base -= 0.2
    if MEMORY["daily_state"] == "overload":
        base -= 0.1

    return max(0.05, min(0.95, base))


def failure_score(task):
    return MEMORY["task_fail_patterns"].get(task, 0)

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
    r = MEMORY["recent_actions"]
    adds = r.count("add")
    dones = r.count("done")

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
    stress = h[-10:].count("overload")
    calm = h[-10:].count("productive")

    MEMORY["emotion_state"] = (
        "stressed" if stress > calm else
        "calm" if calm > stress else "neutral"
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
        return "Yeah."

    if t in ["bye", "goodbye"]:
        return "Later."

    return None

# -------------------------
# SPEECH ENGINE
# -------------------------
def messify(base, arc, emotion, rel):

    p = personality()
    identity = MEMORY.get("identity", "planner")

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

    if identity == "procrastinator":
        text += " You’re stalling again."
    elif identity == "grinder":
        text += " You’re steady."

    if rel > 60 and random.random() < 0.2:
        text = "Still here? " + text

    return text.strip()

# -------------------------
# CORE REPLY
# -------------------------
def reply(text):

    MEMORY["conversations"] += 1

    update_daily_state()

    if text == "week":
        w = MEMORY["weekly_stats"]
        return f"Week:\nAdds: {w['adds']}\nDone: {w['done']}\nIdentity: {MEMORY.get('identity','?')}", "default"

    if text.startswith("add"):
        task = text.replace("add", "", 1).strip()
        save_task(task)
        MEMORY["tasks_added"] += 1
        MEMORY["weekly_stats"]["adds"] += 1
        track_action("add")
        return "Got it.", "task_added"

    if text.startswith("done"):
        task = text.replace("done", "", 1).strip()
        ok = mark_done(task)
        track_action("done")

        if ok:
            MEMORY["tasks_done"] += 1
            MEMORY["weekly_stats"]["done"] += 1
            return "Done.", "task_done"

        return "Not found.", "default"

    if text == "focus":
        tasks = pending_tasks()
        if not tasks:
            return "Nothing left.", "default"

        t = extract_title(tasks[0])
        p = predict_task(t)

        if p < 0.3:
            return f"You’ll probably avoid this → {t}", "default"

        return "Do this → " + t, "default"

    if text == "list":
        tasks = pending_tasks()
        if not tasks:
            return "Nothing left.", "default"
        return "Here’s the board:\n- " + "\n- ".join(extract_title(t) for t in tasks), "default"

    return "Yo.", "default"

# -------------------------
# GIF SYSTEM
# -------------------------
GIFS = {
    "task_added": ["CgACAgQAAxkBAAIFpGo_i6l-7y4q7oZeumVRjAMha46MAAJMBgACCpJFUc5OZtXsmw9OPAQ"],
    "task_done": [
        "CgACAgQAAxkBAANvaj0LBnguOITXUPIWodCIx7BUCGsAArYDAAKCb51QTuahwuylJAk8BA"
    ],
    "default": [
        "CgACAgQAAxkBAANwaj0LDR9fIlU9WkEigLOHE5sV2wMAAiQDAAIqpyxTGZ0lrfl2IpQ8BA"
    ]
}


def get_gif(event):
    return random.choice(GIFS.get(event, GIFS["default"]))


async def send_gif(update: Update, context: ContextTypes.DEFAULT_TYPE, event: str):
    try:
        gif = get_gif(event)
        await context.bot.send_animation(
            chat_id=update.effective_chat.id,
            animation=gif
        )
    except:
        pass

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
        compute_identity()

        base, event = reply(text)

        final = messify(base, MEMORY["arc_state"], MEMORY["emotion_state"], MEMORY["relationship"])

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
