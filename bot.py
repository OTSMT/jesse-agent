import os
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters
from notion_client import Client
from openai import OpenAI

# ENV
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
NOTION_DB_ID = os.getenv("NOTION_DB_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

notion = Client(auth=NOTION_API_KEY)
ai = OpenAI(api_key=OPENAI_API_KEY)

# JESSE BRAIN
def jesse_reply(text):
    try:
        res = ai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are Jesse Pinkman. Casual, funny, chaotic, helpful. Occasionally say bitch."
                },
                {
                    "role": "user",
                    "content": text
                }
            ]
        )

        return res.choices[0].message.content

    except Exception:
    return jesse_free_reply(text)

# SAVE TASK TO NOTION
def save_task(task):
    notion.pages.create(
        parent={"database_id": NOTION_DB_ID},
        properties={
            "Task": {
                "title": [{"text": {"content": task}}]
            },
            "Status": {
                "select": {"name": "Pending"}
            }
        }
    )

# MESSAGE HANDLER
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    # simple task detection
    if text.lower().startswith("add "):
        task = text[4:]
        save_task(task)
        reply = f"Got it. Added '{task}' to the list. Don't slack, bitch."
    else:
        reply = jesse_reply(text)

    await update.message.reply_text(reply)

import random

def jesse_free_reply(text):
    text = text.lower()

    if "add " in text:
        return "Got it. Added to the list, bitch. Don't ghost your own tasks."

    if "done" in text or "finished" in text or "completed" in text:
        return "Hell yeah. That's a win. Keep stacking those, bitch."

    if "help" in text:
        return "Alright, I'm here. Tell me what needs doing."

    if "today" in text or "schedule" in text:
        return "Let's get organized. Check your missions and handle business."

    if "tired" in text or "lazy" in text or "can't" in text:
        return "Yeah, I hear you. But we ain't quitting today, bitch."

    if "hello" in text or "hi" in text:
        return "Yo! Jesse's online. What are we getting done today?"

    return random.choice([
        "Got it. I'm tracking it, bitch.",
        "Alright, I hear you. Keep moving.",
        "Noted. Let's make it happen.",
        "Okay, that's on the radar."
    ])

# START BOT
app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

app.run_polling()
