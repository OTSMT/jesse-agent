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
# TASKS (UNCHANGED)
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
# JESSE STREAK / BEHAVIOR (UNCHANGED)
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
    overload = recent.count("overload")
    idle = recent.count("idle")
    productive = recent.count("productive")

    if overload >= 3:
        MEMORY["arc_state"] = "strict"
    elif productive >= 3:
        MEMORY["arc_state"] = "locked_in"
    else:
        MEMORY["arc_state"] = "supportive"


def detect_emotion():
    recent = MEMORY["recent_actions"]
    tasks = len(pending_tasks())

    adds = recent.count("add")
    dones = recent.count("done")

    if tasks == 0:
        MEMORY["emotion_state"] = "relieved"
    elif adds > dones + 2:
        MEMORY["emotion_state"] = "stressed"
    elif dones > adds:
        MEMORY["emotion_state"] = "proud"
    else:
        MEMORY["emotion_state"] = "neutral"

# -------------------------
# HUMAN LAYER (UNCHANGED)
# -------------------------
HUMAN_INPUTS = {
    "greet": ["hi", "hello", "hey", "yo", "sup"],
    "thanks": ["thanks", "thank you", "thx"],
    "bye": ["bye", "goodbye", "later"]
}

HUMAN_RESPONSES = {
    "greet": ["Yo.", "What’s up.", "Yeah?", "I’m here.", "Yo yo."],
    "thanks": ["Yeah.", "No problem.", "We good.", "All good."],
    "bye": ["Later.", "Aight.", "Stay safe.", "We done here."]
}


def handle_human(text):
    t = text.lower().strip()
    for k, words in HUMAN_INPUTS.items():
        if t in words:
            return random.choice(HUMAN_RESPONSES[k])
    return None

# -------------------------
# 🔥 JESSE SLANG UPGRADED (BIG EXPANSION)
# -------------------------
JESSE_LINES = {
    "task_added": [
        "Yeah, bitch, I got it.",
        "Alright alright, it's in.",
        "Done. Don’t rush me, yo.",
        "Fine, fine, I got it in.",
        "Locked in, bitch.",
        "Alright, we cooking.",
        "Say less, I’m on it.",
        "Yo chill, I added it.",
        "Boom. Done.",
        "Yeah yeah yeah, it’s in the system."
    ],
    "task_done": [
        "YEAH BITCH!",
        "Done. Finally, yo.",
        "Clean as hell.",
        "We straight up cooking.",
        "That’s gone, bitch.",
        "Hell yeah.",
        "Nice. One less problem.",
        "Boom. Deleted from existence.",
        "We’re moving, yo.",
        "That felt good, not gonna lie."
    ],
    "not_found": [
        "Yo… that ain’t even there.",
        "Nah, I don’t see that shit.",
        "You trippin’, it’s not in here.",
        "Bro what? That doesn’t exist.",
        "I looked. Nothing.",
        "That task ghosted me, yo."
    ],
    "list": [
        "Alright, here’s the mess:",
        "Yo… this is your board:",
        "We got this going on:",
        "Don’t cry, but here it is:",
        "This is what we dealing with:"
    ],
    "empty": [
        "Nothing. Clean as hell.",
        "We done. For once.",
        "Bro… it’s EMPTY. Damn.",
        "No tasks. That’s suspiciously peaceful.",
        "We actually free right now."
    ],
    "focus": [
        "Do this → ",
        "Yo, focus on this → ",
        "Start here → ",
        "Only this, don’t overthink → ",
        "Fix this first → "
    ]
}

# -------------------------
# CORE LOGIC (UNCHANGED)
# -------------------------
def reply(text):
    task_count = len(pending_tasks())
    MEMORY["conversations"] += 1

    human = handle_human(text)
    if human:
        return human, "default"

    if text == "list":
        tasks = pending_tasks()
        if not tasks:
            return "Nothing left.", "empty"
        body = "\n- ".join(extract_title(t) for t in tasks)
        return random.choice(JESSE_LINES["list"]) + "\n- " + body, "list"

    if text == "focus":
        tasks = pending_tasks()
        if not tasks:
            return "Nothing left.", "empty"
        return random.choice(JESSE_LINES["focus"]) + extract_title(tasks[0]), "focus"

    if text.startswith("add"):
        task = text.replace("add", "", 1).strip()
        save_task(task)
        MEMORY["tasks_added"] += 1
        track_action("add")
        return random.choice(JESSE_LINES["task_added"]), "task_added"

    if text.startswith("done"):
        task = text.replace("done", "", 1).strip()
        ok = mark_done(task)
        track_action("done")

        if ok:
            MEMORY["tasks_done"] += 1
            return random.choice(JESSE_LINES["task_done"]), "task_done"

        return random.choice(JESSE_LINES["not_found"]), "default"

    return "Yo.", "default"

# -------------------------
# GIF SYSTEM (UNCHANGED WORKING VERSION)
# -------------------------
GIFS = {
    "task_added": [
        "CgACAgQAAxkBAAIFpGo_i6l-7y4q7oZeumVRjAMha46MAAJMBgACCpJFUc5OZtXsmw9OPAQ"
    ],
    "task_done": [
        "CgACAgQAAxkBAANvaj0LBnguOITXUPIWodCIx7BUCGsAArYDAAKCb51QTuahwuylJAk8BA",
        "CgACAgQAAxkBAAIEeWo_F9QX-x12U1EejZaXVvwcHPtsAAJKAwACaoAEU0BH5rBCYtisPAQ"
    ],
    "focus": [
        "CgACAgQAAxkBAAIFpGo_i6l-7y4q7oZeumVRjAMha46MAAJMBgACCpJFUc5OZtXsmw9OPAQ"
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
    except Exception as e:
        print("GIF ERROR:", e)

# -------------------------
# HANDLER (FIXED)
# -------------------------
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = update.message.text.lower().strip()

        response, event = reply(text)

        update_streak()
        update_behavior_history()
        determine_arc_state()
        detect_emotion()

        save_memory(MEMORY)

        await update.message.reply_text(response)
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
