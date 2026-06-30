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

        "last_messages": [],
        "last_reply_time": None,
        "repeat_block": "",

        "task_memory": {},
        "weekly_stats": {
            "adds": 0,
            "done": 0,
            "week_start": str(datetime.date.today()),
        },

        "task_emotions": {},
        "task_fail_patterns": {},

        # 4.0 ADDITIONS
        "weekly_history": [],
        "last_week_summary": None,
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
# WEEK SYSTEM (JESSE 4.0 CORE)
# -------------------------
def check_week_reset():
    today = datetime.date.today()
    start = datetime.datetime.strptime(MEMORY["weekly_stats"]["week_start"], "%Y-%m-%d").date()

    if (today - start).days >= 7:
        MEMORY["weekly_history"].append(dict(MEMORY["weekly_stats"]))

        MEMORY["weekly_stats"] = {
            "adds": 0,
            "done": 0,
            "week_start": str(today),
        }

# -------------------------
# TASK INTELLIGENCE
# -------------------------
def task_score(task):
    age = MEMORY["task_memory"].get(task, {}).get("mentions", 0)
    fails = MEMORY["task_fail_patterns"].get(task, 0)
    return age + (fails * 3)


def failure_level(task):
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
    if len(h) < 3:
        return

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
# WEEKLY SUMMARY (JESSE 4.0)
# -------------------------
def weekly_summary():
    w = MEMORY["weekly_stats"]
    return (
        f"Weekly report:\n"
        f"- Tasks added: {w['adds']}\n"
        f"- Tasks done: {w['done']}\n"
        f"- Active streak week: {len(MEMORY['weekly_history'])}"
    )

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

    if rel > 60 and random.random() < 0.2:
        text = "I’ve seen this before. " + text

    return text.strip()

# -------------------------
# CORE REPLY
# -------------------------
def reply(text):

    MEMORY["conversations"] += 1
    track_action("other")

    # WEEK RESET CHECK
    check_week_reset()

    if text == "week":
        return weekly_summary(), "default"

    if text.startswith("add"):
        task = text.replace("add", "", 1).strip()
        save_task(task)

        MEMORY["tasks_added"] += 1
        track_action("add")
        MEMORY["weekly_stats"]["adds"] += 1

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
        score = task_score(t)

        if score > 12:
            return f"You’ve been avoiding this → {t}", "focus"
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
# GIF SYSTEM
# -------------------------
GIFS = {
    "task_added": [
        "CgACAgQAAxkBAAIFpGo_i6l-7y4q7oZeumVRjAMha46MAAJMBgACCpJFUc5OZtXsmw9OPAQ"
    ],
    "task_done": [
        "CgACAgQAAxkBAANvaj0LBnguOITXUPIWodCIx7BUCGsAArYDAAKCb51QTuahwuylJAk8BA",
        "CgACAgQAAxkBAANuaj0K_bkzP8ZcOpEHDLI1WXXQtSYAAlgIAAIVdXxRISrlCSjFWs88BA"
    ],
    "default": [
        "CgACAgQAAxkBAANwaj0LDR9fIlU9WkEigLOHE5sV2wMAAiQDAAIqpyxTGZ0lrfl2IpQ8BA",
        "CgACAgQAAxkBAANyaj0LJVuPaT_cfd4RvqIivMF4vdMAAv4CAAKzsAxTGIFPam3qjak8BA"
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
