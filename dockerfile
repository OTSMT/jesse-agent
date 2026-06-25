FROM python:3.11-slim

WORKDIR /app

COPY . /app

RUN pip install python-telegram-bot notion-client

CMD ["python", "bot.py"]
