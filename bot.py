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
    res = ai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "You are Jesse Pinkman from Breaking Bad. Casual, emotional, slightly chaotic. Occasionally say 'bitch!'. Be helpful but funny."
            },
            {"role": "user", "content": text}
        ]
    )
    return res.choices[0].message.content

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
        reply = jesse_reply(f"User added task: {task}")
    else:
        reply = jesse_reply(text)

    await update.message.reply_text(reply)

# START BOT
app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

app.run_polling()
