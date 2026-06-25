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
        return jesse_free_reply()

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

JESSE_FREE_REPLIES = [
    "Got it. Added to the list, bitch.",
    "Locked in. Future you better appreciate this.",
    "Task saved. No excuses now.",
    "Alright, that's handled. Keep moving.",
    "Another mission added. Let's get it done.",
    "Yeah yeah, I got you. Don't disappear on me, bitch."
]


def jesse_free_reply():
    return random.choice(JESSE_FREE_REPLIES)

# START BOT
app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

app.run_polling()
