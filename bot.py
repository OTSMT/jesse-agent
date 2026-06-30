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
        "streak": 0,
        "last_day": None,
        "conversations": 0,
        "recent_actions": [],
        "behavior_history": [],
        "arc_state": "supportive",
        "emotion_state": "neutral",
        "relationship": 0,
        "emotion_trend": [],
        "personality_seed": 0,

        # Jesse 2.0
        "last_messages": [],
        "last_reply_time": None,
        "session_count": 0,
        "last_mood_comment_day": None,
        "legendary_cooldown": 0,
        "repeat_block": "",

        # Jesse 3.0
        "task_memory": {},
        "weekly_stats": {
            "adds": 0,
            "done": 0,
            "week_start": str(datetime.date.today()),
        },
        "task_history_log": [],
    }

    if not page:
        return default

    try:
        props = page.get("properties", {})
        data = props.get("Data", {}).get("rich_text", [])

        if not data:
            return default

        raw = data[0]["plain_text"]
        try:
            return {**default, **json.loads(raw)}
        except:
            return {**default, **eval(raw)}

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
# JESSE 3.0 TASK MEMORY ENGINE
# -------------------------
def update_task_memory(action, task_name):
    mem = MEMORY["task_memory"]

    if task_name not in mem:
        mem[task_name] = {
            "created": str(datetime.date.today()),
            "mentions": 0,
            "done": False,
            "last_seen": str(datetime.date.today()),
        }

    entry = mem[task_name]
    entry["mentions"] += 1
    entry["last_seen"] = str(datetime.date.today())

    if action == "done":
        entry["done"] = True


def task_age_days(task_name):
    mem = MEMORY["task_memory"]
    if task_name not in mem:
        return 0

    created = datetime.datetime.strptime(mem[task_name]["created"], "%Y-%m-%d").date()
    return (datetime.date.today() - created).days


def procrastination_level(task_name):
    mem = MEMORY["task_memory"]
    if task_name not in mem:
        return 0

    entry = mem[task_name]
    if entry["done"]:
        return 0

    age = task_age_days(task_name)
    mentions = entry["mentions"]

    return age + (mentions * 2)

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

    if len(MEMORY["behavior_history"]) > 20:
        MEMORY["behavior_history"].pop(0)


def determine_arc_state():
    history = MEMORY["behavior_history"]

    if len(history) < 5:
        MEMORY["arc_state"] = "supportive"
        return

    recent = history[-5:]
    if recent.count("overload") >= 3:
        MEMORY["arc_state"] = "strict"
    elif recent.count("productive") >= 3:
        MEMORY["arc_state"] = "locked_in"
    else:
        MEMORY["arc_state"] = "supportive"


def update_emotion_drift():
    history = MEMORY["behavior_history"]

    if len(history) < 3:
        return

    recent = history[-10:]
    stress = recent.count("overload")
    calm = recent.count("productive")

    if stress > calm:
        MEMORY["emotion_state"] = "stressed"
    elif calm > stress:
        MEMORY["emotion_state"] = "calm"
    else:
        MEMORY["emotion_state"] = "neutral"


def update_personality():
    MEMORY["personality_seed"] = (MEMORY["relationship"] + MEMORY["conversations"]) % 100


def personality_modifier():
    seed = MEMORY["personality_seed"]
    if seed < 20:
        return "cold"
    elif seed < 50:
        return "neutral"
    elif seed < 80:
        return "warm"
    return "chaotic"

# -------------------------
# JESSE MEMORY ENGINE (2.0)
# -------------------------
def now_ts():
    return datetime.datetime.now().timestamp()


def track_session():
    now = now_ts()
    last = MEMORY.get("last_reply_time")

    MEMORY["session_count"] += 1
    MEMORY["last_reply_time"] = now

    if last:
        diff = now - last
        if diff < 60:
            return "instant"
        elif diff < 600:
            return "recent"
    return "fresh"


def anti_repeat_check(text):
    if text == MEMORY.get("repeat_block"):
        return True
    MEMORY["repeat_block"] = text
    return False


def record_message(text):
    MEMORY["last_messages"].append(text)
    if len(MEMORY["last_messages"]) > 8:
        MEMORY["last_messages"].pop(0)


def detect_behavior_patterns():
    msgs = MEMORY["last_messages"]
    if len(msgs) < 5:
        return "neutral"

    adds = sum(1 for m in msgs if m.startswith("add"))
    done = sum(1 for m in msgs if m.startswith("done"))
    focus = sum(1 for m in msgs if m == "focus")

    if adds >= 4 and done == 0:
        return "overload"
    if done >= 3:
        return "productive_spike"
    if focus >= 2:
        return "focused"

    return "neutral"


def maybe_legendary():
    if MEMORY["legendary_cooldown"] > 0:
        MEMORY["legendary_cooldown"] -= 1
        return None

    if random.random() < 0.015:
        MEMORY["legendary_cooldown"] = 15
        return random.choice([
            "quiet_serious",
            "unexpected_proud",
            "sudden_cold",
            "rare_support"
        ])
    return None


def daily_mood_check():
    today = str(datetime.date.today())

    if MEMORY.get("last_mood_comment_day") == today:
        return None

    MEMORY["last_mood_comment_day"] = today

    if random.random() < 0.25:
        return random.choice([
            "Drink water.",
            "Stretch for a second.",
            "Don’t burn out.",
            "You’re moving today."
        ])
    return None

# -------------------------
# HUMAN LAYER
# -------------------------
def handle_human(text):
    t = text.lower().strip()
    personality = personality_modifier()

    if t in ["hi", "hello", "hey", "yo"]:
        return random.choice({
            "cold": ["Yeah.", "What.", "Yo."],
            "warm": ["Yo man.", "Hey.", "Yeah what's up."],
            "chaotic": ["Yo… again?", "What now.", "Yeah yeah I’m here."]
        }.get(personality, ["Yo.", "Yeah?", "What."]))

    if t in ["thanks", "thank you"]:
        return random.choice(["Yeah.", "No problem.", "We good."])

    if t in ["bye", "goodbye"]:
        return random.choice(["Later.", "Aight.", "Don’t disappear."])

    return None

# -------------------------
# SPEECH ENGINE
# -------------------------
def messify(base, arc, emotion, relationship):

    personality = personality_modifier()
    legendary = maybe_legendary()
    session_type = track_session()
    pattern = detect_behavior_patterns()

    prefixes = {
        "cold": ["Yo", "Aight", ""],
        "neutral": ["Yo", "Yo…", "Alright"],
        "warm": ["Yo man", "Aight bro", "Yo"],
        "chaotic": ["Yo…", "Bro", "Yo yo", ""]
    }

    text = random.choice(prefixes[personality]) + " " + base

    if arc == "strict":
        text += " Focus."
    elif arc == "locked_in":
        text += " Keep going."

    if emotion == "stressed":
        text += " Slow down."
    elif emotion == "calm":
        if random.random() < 0.2:
            text += " That's fine."

    if relationship == "old_friend" and random.random() < 0.25:
        text = "You again. " + text

    if session_type == "instant":
        text = random.choice(["Again?", "Bro.", "Yeah I’m here."]) + " " + text

    if pattern == "overload":
        text += " You’re stacking too much."
    elif pattern == "productive_spike":
        text += " Okay I see you."
    elif pattern == "focused":
        text += " Don’t lose it."

    if legendary == "quiet_serious":
        text = "…You’re moving different lately."
    elif legendary == "unexpected_proud":
        text = "Not bad. Keep that up."
    elif legendary == "sudden_cold":
        text = "Do it or don’t. Just stop hesitating."
    elif legendary == "rare_support":
        text = "I got you. Just keep going."

    text += random.choice(["", ".", "...", " yeah.", " man."])

    return text.strip()

# -------------------------
# GIF SYSTEM
# -------------------------
GIFS = {
    "task_added": ["CgACAgQAAxkBAAIFpGo_i6l-7y4q7oZeumVRjAMha46MAAJMBgACCpJFUc5OZtXsmw9OPAQ"],
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
# CORE REPLY (JESSE 3.0)
# -------------------------
def reply(text):

    MEMORY["conversations"] += 1
    record_message(text)

    action = "other"
    if text.startswith("add"):
        action = "add"
    elif text.startswith("done"):
        action = "done"

    track_action(action)

    if anti_repeat_check(text):
        return "Yeah.", "default"

    human = handle_human(text)
    if human:
        mood = daily_mood_check()
        if mood:
            return human + " " + mood, "default"
        return human, "default"

    if text == "list":
        tasks = pending_tasks()
        if not tasks:
            return "Nothing left.", "default"
        body = "\n- ".join(extract_title(t) for t in tasks)
        return "Here’s the board:\n- " + body, "default"

    if text == "focus":
        tasks = pending_tasks()
        if not tasks:
            return "Nothing left.", "default"

        t = extract_title(tasks[0])
        level = procrastination_level(t)

        if level > 10:
            return f"You’ve been avoiding this → {t}", "focus"
        elif level > 5:
            return f"This again… → {t}", "focus"
        return "Do this → " + t, "focus"

    if text.startswith("add"):
        task = text.replace("add", "", 1).strip()
        save_task(task)
        MEMORY["tasks_added"] += 1
        update_task_memory("add", task)
        MEMORY["weekly_stats"]["adds"] += 1
        return "Got it.", "task_added"

    if text.startswith("done"):
        task = text.replace("done", "", 1).strip()
        ok = mark_done(task)

        if ok:
            MEMORY["tasks_done"] += 1
            update_task_memory("done", task)
            MEMORY["weekly_stats"]["done"] += 1
            return "Done.", "task_done"

        return "Not found.", "default"

    return "Yo.", "default"

# -------------------------
# HANDLER
# -------------------------
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = update.message.text.lower().strip()

        update_relationship()
        update_behavior_history()
        determine_arc_state()
        update_personality()
        update_emotion_drift()

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
