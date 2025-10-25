import logging
import sys
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional
from urllib.parse import urlparse, urlunparse

import requests
from requests import RequestException
from telebot import TeleBot, types
from telebot.apihelper import ApiTelegramException

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from api.config import BASE_API_URL, TELEGRAM_TOKEN

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

API_TIMEOUT = (5, 90)
MAX_MESSAGE_LENGTH = 4096
RATE_LIMIT_SECONDS = 5

bot = TeleBot(TELEGRAM_TOKEN, parse_mode="Markdown")
last_message_at: Dict[int, float] = {}


def markdown_escape(text: str) -> str:
    """Escape Telegram Markdown control characters in dynamic text."""
    return (
        text.replace("\\", "\\\\")
        .replace("_", "\\_")
        .replace("*", "\\*")
        .replace("[", "\\[")
        .replace("`", "\\`")
    )


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
    if delta < RATE_LIMIT_SECONDS:
        return int(RATE_LIMIT_SECONDS - delta)

    last_message_at[chat_id] = now
    return None


def fetch_manifest() -> Iterable[dict]:
    response = requests.get(build_url("/manifest"), timeout=API_TIMEOUT)
    response.raise_for_status()
    data = response.json()
    return data or []


def ask_question(question: str) -> dict:
    payload = {"question": question}
    response = requests.post(
        build_url("/ask"),
        json=payload,
        timeout=API_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def send_markdown(chat_id: int, text: str, reply_markup: Optional[types.InlineKeyboardMarkup] = None) -> None:
    chunks = chunk_message(text)
    for index, chunk in enumerate(chunks):
        markup = reply_markup if index == len(chunks) - 1 else None
        bot.send_message(chat_id, chunk, reply_markup=markup, disable_web_page_preview=False)


def normalize_public_url(url: str) -> Optional[str]:
    if not url:
        return None
    try:
        parsed = urlparse(url)
    except Exception:
        return None
    if parsed.scheme not in {"http", "https"}:
        return None
    host = parsed.hostname or ""
    if host in {"localhost", "0.0.0.0"}:
        parsed = parsed._replace(netloc=parsed.netloc.replace(host, "127.0.0.1"))
    return urlunparse(parsed)


@bot.message_handler(commands=["start"])
def handle_start(message: types.Message) -> None:
    name = message.from_user.first_name or "коллега"
    greeting = (
        f"Привет, {markdown_escape(name)}!\n"
        "Я помогу быстро найти ответы по документам «Летово». "
        "Спроси меня что угодно про приём, учёбу или регламенты."
    )
    bot.reply_to(message, greeting)


@bot.message_handler(commands=["help"])
def handle_help(message: types.Message) -> None:
    help_text = (
        "Я отвечаю на вопросы по документам школы и могу показать список файлов (/docs).\n"
        "Просто напиши вопрос, и я пришлю краткий ответ с ссылками на источники."
    )
    bot.reply_to(message, help_text)


@bot.message_handler(commands=["docs"])
def handle_docs(message: types.Message) -> None:
    wait_for = rate_limit(message.chat.id)
    if wait_for is not None:
        bot.reply_to(
            message,
            f"Слишком часто. Подождите ещё {wait_for} с.",
        )
        return

    bot.send_chat_action(message.chat.id, "typing")

    try:
        manifest = list(fetch_manifest())
    except RequestException as exc:
        logging.exception("Failed to fetch manifest")
        bot.reply_to(message, "Не удалось получить список документов. Попробуйте позже.")
        return

    if not manifest:
        bot.reply_to(message, "Документы пока не загружены.")
        return

    lines = []
    for item in manifest:
        title = markdown_escape(item.get("title") or "Без названия")
        url = item.get("url")
        if url:
            lines.append(f"- [{title}]({url})")
        else:
            lines.append(f"- {title}")

    send_markdown(message.chat.id, "\n".join(lines))


@bot.message_handler(func=lambda message: True, content_types=["text"])
def handle_message(message: types.Message) -> None:
    wait_for = rate_limit(message.chat.id)
    if wait_for is not None:
        bot.reply_to(
            message,
            f"Слишком часто. Подождите ещё {wait_for} с.",
        )
        return

    bot.send_chat_action(message.chat.id, "typing")
    status_msg = bot.send_message(
        message.chat.id,
        "🤖 Собираю ответ…",
        disable_notification=True,
    )

    try:
        result = ask_question(message.text)
    except RequestException:
        logging.exception("Failed to contact API")
        try:
            bot.edit_message_text(
                "Сервис временно недоступен. Попробуйте позже.",
                message.chat.id,
                status_msg.message_id,
            )
        except ApiTelegramException:
            bot.reply_to(message, "Сервис временно недоступен. Попробуйте позже.")
        return

    answer_text = result.get("text") or "Ответ не найден."
    sources = result.get("sources") or []

    markup: Optional[types.InlineKeyboardMarkup] = None
    buttons: List[types.InlineKeyboardButton] = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        url = normalize_public_url(source.get("url"))
        if not url:
            continue
        buttons.append(types.InlineKeyboardButton(text="Открыть документ", url=url))

    if buttons:
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(*buttons)

    try:
        bot.edit_message_text(
            "🔎 Нашёл информацию, отправляю…",
            message.chat.id,
            status_msg.message_id,
        )
    except ApiTelegramException:
        pass

    try:
        send_markdown(message.chat.id, answer_text, reply_markup=markup)
    except ApiTelegramException as exc:
        logging.exception("Failed to send answer message (retrying without buttons)")
        if markup:
            send_markdown(message.chat.id, answer_text)
        else:
            raise exc
    finally:
        try:
            bot.delete_message(message.chat.id, status_msg.message_id)
        except ApiTelegramException:
            pass


def main() -> None:
    logging.info("Starting Telegram bot")
    bot.infinity_polling(skip_pending=True, allowed_updates=["message"])


if __name__ == "__main__":
    main()
