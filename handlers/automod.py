import re
from urllib.parse import urlparse
from vkbottle.bot import BotLabeler, Message
from database.db import db
from utils.vk_helpers import delete_message_safe
from utils.action_logger import log_moderation_action
from handlers.moderation import execute_auto_punishment

automod_labeler = BotLabeler()

# Базовый регулярный фильтр нецензурной лексики (корни слов)
BAD_WORDS_RE = re.compile(
    r"\b(ху[йеяюи]|пизд[ауеыой]|еб[ауоеиытл]|бля[дтс]?|сук[аи]|пид[оа]?р|гандон|шлюх[аи]|мудак)\w*",
    re.IGNORECASE
)

# Ссылки на беседы ВК (инвайты)
INVITE_LINK_RE = re.compile(
    r"(?:https?://)?(?:m\.)?vk\.(?:com|me)/join/[a-zA-Z0-9_\-/=]+",
    re.IGNORECASE
)

# Общий паттерн URL-ссылок
URL_RE = re.compile(
    r"(?:https?://|www\.)[a-zA-Z0-9\-]+(?:\.[a-zA-Z0-9\-]+)+(?:/[^\s]*)?",
    re.IGNORECASE
)

def is_caps_abuse(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    if len(letters) < 12:
        return False
    upper_count = sum(1 for c in letters if c.isupper())
    return (upper_count / len(letters)) > 0.75

def has_forbidden_links(text: str, whitelist_csv: str) -> bool:
    whitelist = {d.strip().lower() for d in whitelist_csv.split(",") if d.strip()}
    for match in URL_RE.finditer(text):
        raw_url = match.group(0)
        if not raw_url.startswith("http"):
            raw_url = "http://" + raw_url
        parsed = urlparse(raw_url)
        domain = (parsed.netloc or "").lower().lstrip("www.")
        if not any(domain == w or domain.endswith("." + w) for w in whitelist):
            return True
    return False

@automod_labeler.message()
async def automod_handler(
    message: Message,
    is_chat: bool = False,
    role_level: int = 1,
    chat_settings: dict = None,
    is_flooding: bool = False,
    is_repeating: bool = False,
    **kwargs
):
    """
    Автомодерация сообщений в беседах (выполняется для обычных участников role_level < 2).
    Проверяет: анти-инвайты, антиссылки, антимат, антиспам (флуд, повтор, капс).
    """
    if not is_chat or role_level >= 2 or not chat_settings:
        return

    text = message.text or ""
    violation_reason = None

    # 1. Анти-инвайты других бесед
    if chat_settings.get("antiinvite", True) and INVITE_LINK_RE.search(text):
        violation_reason = "Ссылки-приглашения в другие беседы запрещены"

    # 2. Анти-ссылки (с проверкой белого списка доменов)
    elif chat_settings.get("antilinks", True) and has_forbidden_links(text, chat_settings.get("whitelist_domains", "")):
        violation_reason = "Сторонние ссылки запрещены"

    # 3. Антимат
    elif chat_settings.get("antimat", True) and BAD_WORDS_RE.search(text):
        violation_reason = "Нецензурная лексика"

    # 4. Антиспам (флуд / повтор / капс)
    elif chat_settings.get("antispam", True):
        if is_flooding:
            violation_reason = "Флуд (слишком частые сообщения)"
        elif is_repeating:
            violation_reason = "Спам одинаковыми сообщениями"
        elif is_caps_abuse(text):
            violation_reason = "Злоупотребление CAPS LOCK"

    if not violation_reason:
        return

    # Удаляем сообщение нарушителя
    await delete_message_safe(message.ctx_api, message.peer_id, [message.conversation_message_id])

    # Выдаем автоматическое предупреждение (варн)
    count = await db.add_warn(message.peer_id, message.from_id, 0, f"[Автомод] {violation_reason}")
    limit = chat_settings.get("warn_limit", 3)
    punishment = chat_settings.get("warn_punishment", "ban")

    await message.answer(
        f"🛡 [id{message.from_id}|Участник], ваше сообщение удалено ({violation_reason}).\n"
        f"⚠️ Выдано предупреждение: {count}/{limit}."
    )
    await log_moderation_action(
        message.ctx_api, message.peer_id, 0, message.from_id,
        "AUTOMOD_WARN", f"{violation_reason} ({count}/{limit})"
    )

    if count >= limit:
        await execute_auto_punishment(message, message.from_id, punishment, violation_reason)
