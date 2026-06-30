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
# TASK SYSTEM (UNCHANGED)
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
# RELATIONSHIP MEMORY
# -------------------------
def update_relationship():
    MEMORY["relationship"] += 1


def relationship_state():
    r = MEMORY["relationship"]
    if r < 10:
        return "new"
    elif r < 30:
        return "familiar"
    elif r < 80:
        return "regular"
    return "old_friend"

# -------------------------
# BEHAVIOR SYSTEM
# -------------------------
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

# -------------------------
# EMOTION DRIFT
# -------------------------
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

    MEMORY["emotion_trend"].append(MEMORY["emotion_state"])
    if len(MEMORY["emotion_trend"]) > 15:
        MEMORY["emotion_trend"].pop(0)

# -------------------------
# PERSONALITY EVOLUTION
# -------------------------
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
# HUMAN LAYER (UNCHANGED LOGIC)
# -------------------------
def handle_human(text):
    t = text.lower().strip()

    emotion = MEMORY.get("emotion_state", "neutral")
    personality = personality_modifier()

    if t in ["hi", "hello", "hey", "yo"]:
        if personality == "cold":
            return random.choice(["Yeah.", "What.", "Yo."])
        if personality == "warm":
            return random.choice(["Yo man.", "Hey.", "Yeah what's up."])
        if personality == "chaotic":
            return random.choice(["Yo… again?", "What now.", "Yeah yeah I’m here."])
        return random.choice(["Yo.", "Yeah?", "What."])

    if t in ["thanks", "thank you"]:
        if emotion == "stressed":
            return random.choice(["Yeah.", "Don’t overdo it though.", "Whatever."])
        return random.choice(["Yeah.", "No problem.", "We good."])

    if t in ["bye", "goodbye"]:
        if personality == "cold":
            return random.choice(["Later.", "Go."])
        return random.choice(["Later.", "Aight.", "Don’t disappear."])

    return None

# -------------------------
# SPEECH ENGINE
# -------------------------
def messify(base, arc, emotion, relationship):

    personality = personality_modifier()

    prefixes = {
        "cold": ["Yo", "Aight", ""],
        "neutral": ["Yo", "Yo…", "Alright"],
        "warm": ["Yo man", "Aight bro", "Yo"],
        "chaotic": ["Yo…", "Bro", "Yo yo", ""]
    }

    hesitations = ["", "...", " I guess.", " whatever.", " man."]
    endings = ["", ".", "…", " yo.", " yeah."]

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

    if personality == "chaotic" and random.random() < 0.3:
        text += " not gonna lie."

    text += random.choice(hesitations)
    text += random.choice(endings)

    return text.strip()

# -------------------------
# CORE LOGIC
# -------------------------
def reply(text):
    MEMORY["conversations"] += 1

    human = handle_human(text)
    if human:
        return human, "default"

    if text == "list":
        tasks = pending_tasks()
        if not tasks:
            return "Nothing left.", "empty"
        body = "\n- ".join(extract_title(t) for t in tasks)
        return "Here’s the board:\n- " + body, "list"

    if text == "focus":
        tasks = pending_tasks()
        if not tasks:
            return "Nothing left.", "empty"
        return "Do this → " + extract_title(tasks[0]), "focus"

    if text.startswith("add"):
        task = text.replace("add", "", 1).strip()
        save_task(task)
        MEMORY["tasks_added"] += 1
        track_action("add")
        return "Got it.", "task_added"

    if text.startswith("done"):
        task = text.replace("done", "", 1).strip()
        ok = mark_done(task)
        track_action("done")

        if ok:
            MEMORY["tasks_done"] += 1
            return "Done.", "task_done"

        return "Not found.", "default"

    return "Yo.", "default"

# -------------------------
# 🔥 UPDATED GIF SYSTEM (YOUR NEW SET)
# -------------------------
GIFS = {
    "task_added": [
        "CgACAgQAAxkBAAIFpGo_i6l-7y4q7oZeumVRjAMha46MAAJMBgACCpJFUc5OZtXsmw9OPAQ"  # Let's cook Jesse
    ],
    "task_done": [
        "CgACAgQAAxkBAANvaj0LBnguOITXUPIWodCIx7BUCGsAArYDAAKCb51QTuahwuylJAk8BA",  # Yeah science happy
        "CgACAgQAAxkBAANuaj0K_bkzP8ZcOpEHDLI1WXXQtSYAAlgIAAIVdXxRISrlCSjFWs88BA",  # Boohoo angry
    ],
    "focus": [
        "CgACAgQAAxkBAAIFpGo_i6l-7y4q7oZeumVRjAMha46MAAJMBgACCpJFUc5OZtXsmw9OPAQ"
    ],
    "default": [
        "CgACAgQAAxkBAANwaj0LDR9fIlU9WkEigLOHE5sV2wMAAiQDAAIqpyxTGZ0lrfl2IpQ8BA",  # yelling bitch
        "CgACAgQAAxkBAANyaj0LJVuPaT_cfd4RvqIivMF4vdMAAv4CAAKzsAxTGIFPam3qjak8BA",  # confused what
        "CgACAgQAAxkBAAIEeWo_F9QX-x12U1EejZaXVvwcHPtsAAJKAwACaoAEU0BH5rBCYtisPAQ",  # dancing
        "CgACAgQAAxkBAANtaj0K7FPuicSUn89jyEwa098jnd0AAk0DAAJZhwRTeB7Y2zkHLno8BA",  # drinking water
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
        determine_arc_state()
        update_personality()
        update_emotion_drift()

        arc = MEMORY["arc_state"]
        emotion = MEMORY["emotion_state"]
        rel = relationship_state()

        response, event = reply(text)

        final = messify(response, arc, emotion, rel)

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
