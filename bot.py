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
        "relationship": 0
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
    if r < 30:
        return "familiar"
    if r < 80:
        return "regular"
    return "old_friend"

# -------------------------
# BEHAVIOR SYSTEM (UNCHANGED LOGIC)
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
# HUMAN LAYER
# -------------------------
def handle_human(text):
    t = text.lower().strip()

    if t in ["hi", "hello", "hey", "yo"]:
        return random.choice([
            "Yo.",
            "Yeah?",
            "…yo.",
            "What.",
            "Yo… you again."
        ])

    if t in ["thanks", "thank you"]:
        return random.choice([
            "Yeah.",
            "Don’t mention it.",
            "Whatever.",
            "Yeah… sure."
        ])

    if t in ["bye", "goodbye"]:
        return random.choice([
            "Later.",
            "Aight.",
            "Don’t disappear.",
            "Yeah yeah, go."
        ])

    return None

# -------------------------
# JESSE SPEECH ENGINE (NEW CORE)
# -------------------------
def messify(base, arc, emotion, relationship):
    prefixes = ["Yo", "Yo…", "Alright", "Fine", "Aight", ""]
    hesitations = ["", "...", " I guess.", " whatever.", " man.", " dude."]
    self_comments = ["", " not gonna lie.", " I guess.", " whatever.", " yeah."]
    endings = ["", ".", "…", " yo.", " let's go."]

    text = random.choice(prefixes) + " " + base

    if arc == "strict":
        text += " Focus up."
    elif arc == "locked_in":
        text += " Keep going."

    if emotion == "stressed":
        text += " Slow down."
    elif emotion == "proud":
        text += " Good."

    # relationship bleed
    if relationship == "old_friend":
        if random.random() < 0.3:
            text = "You again. " + text

    # imperfection injection
    text += random.choice(hesitations)
    if random.random() < 0.4:
        text += random.choice(self_comments)

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

    return "…", "default"

# -------------------------
# GIF SYSTEM (UNCHANGED)
# -------------------------
GIFS = {
    "task_added": ["GIF1"],
    "task_done": ["GIF2"],
    "focus": ["GIF3"],
    "default": ["GIF4"]
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

        arc = MEMORY["arc_state"]
        emotion = MEMORY.get("emotion_state", "neutral")
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
