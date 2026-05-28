"""Telegram-бот школы «Летово». Работает на общем бэкенде (/query), ответы идентичны вебу.

Сообщения отправляются обычным текстом (без Markdown) — это надёжно: тексты ответов могут
содержать «*», «_», «[», которые ломают парсинг Markdown в Telegram. Голые URL Telegram
делает кликабельными автоматически; плюс к каждому источнику добавляется inline-кнопка.
"""
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlparse, urlunparse

import requests
from requests import RequestException
from telebot import TeleBot, types
from telebot.apihelper import ApiTelegramException

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from telegram.config import (
    API_TIMEOUT,
    BASE_API_URL,
    DAILY_REQUEST_LIMIT,
    MESSAGE_RATE_SECONDS,
    TELEGRAM_TOKEN,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

MAX_MESSAGE_LENGTH = 4096

bot = TeleBot(TELEGRAM_TOKEN)  # без parse_mode → отправляем как обычный текст
last_message_at: Dict[int, float] = {}
daily_usage: Dict[int, Tuple[str, int]] = {}


def build_url(path: str) -> str:
    base = BASE_API_URL.rstrip("/")
    suffix = path if path.startswith("/") else f"/{path}"
    return f"{base}{suffix}"


def chunk_message(text: str, limit: int = MAX_MESSAGE_LENGTH) -> List[str]:
    if len(text) <= limit:
        return [text]
    parts: List[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= limit:
            parts.append(remaining)
            break
        chunk = remaining[:limit]
        split_at = max(chunk.rfind("\n"), chunk.rfind(". "))
        if split_at == -1 or split_at < limit // 2:
            split_at = chunk.rfind(" ")
        if split_at == -1:
            split_at = limit
        parts.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip()
    return parts


def rate_limit(chat_id: int) -> Optional[int]:
    now = time.time()
    last_seen = last_message_at.get(chat_id, 0.0)
    delta = now - last_seen
    if delta < MESSAGE_RATE_SECONDS:
        return int(MESSAGE_RATE_SECONDS - delta)
    last_message_at[chat_id] = now
    return None


def consume_daily_quota(chat_id: int) -> Optional[int]:
    today = datetime.now(timezone.utc).date().isoformat()
    stored = daily_usage.get(chat_id)
    count = 0
    if stored:
        stored_day, stored_count = stored
        if stored_day == today:
            count = stored_count
    if count >= DAILY_REQUEST_LIMIT:
        return None
    count += 1
    daily_usage[chat_id] = (today, count)
    return DAILY_REQUEST_LIMIT - count


def fetch_manifest() -> Iterable[dict]:
    response = requests.get(build_url("/manifest"), timeout=API_TIMEOUT)
    response.raise_for_status()
    return response.json() or []


def ask_question(question: str) -> dict:
    response = requests.post(build_url("/query"), json={"question": question}, timeout=API_TIMEOUT)
    response.raise_for_status()
    return response.json()


def send_text(chat_id: int, text: str, reply_markup: Optional[types.InlineKeyboardMarkup] = None) -> None:
    chunks = chunk_message(text)
    for index, chunk in enumerate(chunks):
        markup = reply_markup if index == len(chunks) - 1 else None
        bot.send_message(chat_id, chunk, reply_markup=markup, disable_web_page_preview=True)


def normalize_public_url(url: str) -> Optional[str]:
    if not url:
        return None
    try:
        parsed = urlparse(url)
    except Exception:
        return None
    if parsed.scheme not in {"http", "https"}:
        return None
    return urlunparse(parsed)


def format_answer(result: dict) -> Tuple[str, Optional[types.InlineKeyboardMarkup]]:
    answer = (result.get("answer") or "").strip() or "Ответ не найден."
    sources = result.get("sources") or []

    lines = [answer]
    buttons: List[types.InlineKeyboardButton] = []
    if sources:
        lines.append("")
        lines.append("Источники:")
        for s in sources:
            if not isinstance(s, dict):
                continue
            title = s.get("title") or "Документ"
            page = s.get("page")
            url = normalize_public_url(s.get("url"))
            suffix = f", стр. {page}" if page else ""
            lines.append(f"• {title}{suffix}")
            if url:
                lines.append(url)
                label = (title[:40]) + (f" — стр. {page}" if page else "")
                buttons.append(types.InlineKeyboardButton(text=label, url=url))

    markup = None
    if buttons:
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(*buttons[:3])
    return "\n".join(lines), markup


@bot.message_handler(commands=["start"])
def handle_start(message: types.Message) -> None:
    name = message.from_user.first_name or "коллега"
    bot.reply_to(
        message,
        f"Привет, {name}!\n"
        "Я помогу быстро найти ответы по официальным документам школы «Летово» и дам ссылку "
        "на страницу первоисточника. Спросите про приём, учёбу или регламенты. /docs — список документов.",
    )


@bot.message_handler(commands=["help"])
def handle_help(message: types.Message) -> None:
    bot.reply_to(
        message,
        "Напишите вопрос по документам школы — я пришлю краткий ответ со ссылками на страницы PDF.\n"
        "/docs — список проиндексированных документов.",
    )


@bot.message_handler(commands=["docs"])
def handle_docs(message: types.Message) -> None:
    wait_for = rate_limit(message.chat.id)
    if wait_for is not None:
        bot.reply_to(message, f"Слишком часто. Подождите ещё {wait_for} с.")
        return
    bot.send_chat_action(message.chat.id, "typing")
    try:
        manifest = list(fetch_manifest())
    except RequestException:
        logging.exception("Failed to fetch manifest")
        bot.reply_to(message, "Не удалось получить список документов. Попробуйте позже.")
        return
    if not manifest:
        bot.reply_to(message, "Документы пока не загружены.")
        return
    lines = []
    for item in manifest:
        title = item.get("title") or "Без названия"
        url = item.get("url")
        lines.append(f"• {title}")
        if url:
            lines.append(url)
    send_text(message.chat.id, "\n".join(lines))


@bot.message_handler(func=lambda message: True, content_types=["text"])
def handle_message(message: types.Message) -> None:
    wait_for = rate_limit(message.chat.id)
    if wait_for is not None:
        bot.reply_to(message, f"Слишком часто. Подождите ещё {wait_for} с.")
        return

    if consume_daily_quota(message.chat.id) is None:
        bot.reply_to(message, f"Дневной лимит {DAILY_REQUEST_LIMIT} запросов исчерпан. Задайте вопрос завтра.")
        return

    bot.send_chat_action(message.chat.id, "typing")
    status_msg = bot.send_message(message.chat.id, "Собираю ответ…", disable_notification=True)

    try:
        result = ask_question(message.text)
    except RequestException:
        logging.exception("Failed to contact API")
        try:
            bot.edit_message_text("Сервис временно недоступен. Попробуйте позже.", message.chat.id, status_msg.message_id)
        except ApiTelegramException:
            bot.reply_to(message, "Сервис временно недоступен. Попробуйте позже.")
        return

    text, markup = format_answer(result)
    try:
        bot.delete_message(message.chat.id, status_msg.message_id)
    except ApiTelegramException:
        pass
    send_text(message.chat.id, text, reply_markup=markup)


def main() -> None:
    logging.info("Starting Telegram bot (backend: %s)", BASE_API_URL)
    bot.infinity_polling(skip_pending=True, allowed_updates=["message"])


if __name__ == "__main__":
    main()
