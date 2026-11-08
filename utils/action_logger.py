import random
from typing import Optional
from vkbottle import API
from loguru import logger
from config import config
from database.db import db
from utils.vk_helpers import api_call_with_retry

async def log_moderation_action(
    api: API,
    peer_id: int,
    actor_id: int,
    target_id: Optional[int],
    action: str,
    details: str = ""
):
    """
    Записывает действие в таблицу logs и отправляет уведомление в LOG_CHAT_ID (беседу или ЛС).
    """
    try:
        await db.log_action(peer_id, actor_id, target_id, action, details)
    except Exception as e:
        logger.error(f"Ошибка записи лога в БД: {e}")

    if not config.log_chat_id:
        return

    chat_num = peer_id - 2000000000 if peer_id > 2000000000 else peer_id
    actor_str = f"[id{actor_id}|Модератор]" if actor_id > 0 else "Автомодератор"
    target_str = f" -> [id{target_id}|Пользователь]" if target_id and target_id > 0 else ""

    text = (
        f"🛡 [ЛОГ МОДЕРАЦИИ]\n"
        f"📍 Чат: {chat_num} (peer: {peer_id})\n"
        f"👤 Кто: {actor_str}{target_str}\n"
        f"⚡ Действие: {action}\n"
        f"📝 Детали: {details or 'Нет'}"
    )

    try:
        await api_call_with_retry(
            api.messages.send,
            peer_id=config.log_chat_id,
            message=text,
            random_id=random.randint(1, 2_000_000_000)
        )
    except Exception as e:
        logger.warning(f"Не удалось отправить лог в LOG_CHAT_ID ({config.log_chat_id}): {e}")
