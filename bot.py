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
        "identity": "planner",

        # 6.0 CORE
        "task_categories": {},
        "avoidance_index": 0,
        "consistency_score": 0,
        "execution_speed": 0,
        "honesty_mode": False,
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
# CATEGORY ENGINE (6.0 CORE)
# -------------------------
def detect_category(text):
    t = text.lower()
    if any(x in t for x in ["email", "form", "invoice", "call"]):
        return "admin"
    if any(x in t for x in ["study", "learn", "read", "course"]):
        return "learning"
    if any(x in t for x in ["work", "project", "report"]):
        return "work"
    if any(x in t for x in ["gym", "health", "run", "sleep"]):
        return "personal"
    return "unknown"


def update_category(task, success):
    cat = detect_category(task)

    if cat not in MEMORY["task_categories"]:
        MEMORY["task_categories"][cat] = {"attempts": 0, "fails": 0}

    MEMORY["task_categories"][cat]["attempts"] += 1
    if not success:
        MEMORY["task_categories"][cat]["fails"] += 1


def category_avoidance_score():
    total_fails = sum(v["fails"] for v in MEMORY["task_categories"].values())
    total_attempts = sum(v["attempts"] for v in MEMORY["task_categories"].values())
    return total_fails / (total_attempts + 1)

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

# -------------------------
# METRICS ENGINE (6.0 CORE)
# -------------------------
def compute_metrics():
    adds = MEMORY["weekly_stats"]["adds"]
    done = MEMORY["weekly_stats"]["done"]

    MEMORY["consistency_score"] = done / (adds + 1)
    MEMORY["avoidance_index"] = category_avoidance_score()
    MEMORY["execution_speed"] = done - adds * 0.2

    MEMORY["honesty_mode"] = MEMORY["avoidance_index"] > 0.6

# -------------------------
# PERSONALITY
# -------------------------
def personality():
    seed = (MEMORY["relationship"] + MEMORY["conversations"]) % 100

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

    if t in ["hi", "hello", "yo", "hey"]:
        return random.choice(["Yo.", "Yeah.", "What."])

    if t in ["thanks", "thank you"]:
        return "Yeah."

    if t in ["bye", "goodbye"]:
        return "Later."

    return None

# -------------------------
# SPEECH ENGINE (6.0)
# -------------------------
def messify(base, arc, emotion, rel):

    p = personality()
    avoidance = MEMORY.get("avoidance_index", 0)

    text = random.choice({
        "cold": ["Yo", "Aight", ""],
        "neutral": ["Yo", "Yo…", "Alright"],
        "warm": ["Yo man", "Aight bro", "Yo"],
        "chaotic": ["Yo…", "Bro", "Yo yo", ""]
    }[p]) + " " + base

    # ARC
    if arc == "strict":
        text += " Focus."
    elif arc == "locked_in":
        text += " Keep going."

    # HONEST MODE
    if MEMORY.get("honesty_mode"):
        text = "You keep avoiding the same patterns. " + text

    if avoidance > 0.7:
        text += " This is becoming a pattern."

    if rel > 60 and random.random() < 0.2:
        text = "Still here? " + text

    return text.strip()

# -------------------------
# CORE REPLY
# -------------------------
def reply(text):

    MEMORY["conversations"] += 1

    if text == "week":
        w = MEMORY["weekly_stats"]
        return f"Week:\nAdds: {w['adds']}\nDone: {w['done']}\nAvoidance: {MEMORY.get('avoidance_index',0):.2f}", "default"

    if text.startswith("add"):
        task = text.replace("add", "", 1).strip()
        save_task(task)

        MEMORY["tasks_added"] += 1
        MEMORY["weekly_stats"]["adds"] += 1

        update_category(task, True)
        track_action("add")

        return "Got it.", "task_added"

    if text.startswith("done"):
        task = text.replace("done", "", 1).strip()
        ok = mark_done(task)

        track_action("done")

        if ok:
            MEMORY["tasks_done"] += 1
            MEMORY["weekly_stats"]["done"] += 1
            update_category(task, True)
            return "Done.", "task_done"

        update_category(task, False)
        return "Not found.", "default"

    if text == "focus":
        tasks = pending_tasks()
        if not tasks:
            return "Nothing left.", "default"

        t = extract_title(tasks[0])

        if MEMORY.get("avoidance_index", 0) > 0.6:
            return f"You keep avoiding similar tasks → {t}", "default"

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
    "task_done": ["CgACAgQAAxkBAANvaj0LBnguOITXUPIWodCIx7BUCGsAArYDAAKCb51QTuahwuylJAk8BA"],
    "default": ["CgACAgQAAxkBAANwaj0LDR9fIlU9WkEigLOHE5sV2wMAAiQDAAIqpyxTGZ0lrfl2IpQ8BA"]
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
        compute_metrics()

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
