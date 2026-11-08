import asyncio
from typing import Set, Tuple
from vkbottle import API, VKAPIError
from loguru import logger

# Кэш админов бесед ВК: {peer_id: (timestamp, set_of_admin_ids, bot_is_admin)}
_CHAT_ADMINS_CACHE = {}
CACHE_TTL = 120.0  # 2 минуты

async def api_call_with_retry(coro_func, *args, retries: int = 3, **kwargs):
    """Обертка для обработки Rate Limit ВК (код 6 — Too many requests per second)."""
    delay = 0.5
    for attempt in range(retries):
        try:
            return await coro_func(*args, **kwargs)
        except VKAPIError as e:
            if e.code == 6 and attempt < retries - 1:
                logger.warning(f"VK Rate limit (Code 6). Повтор через {delay} сек...")
                await asyncio.sleep(delay)
                delay *= 2
            else:
                raise

async def get_vk_chat_admins(api: API, peer_id: int, group_id: int, force_refresh: bool = False) -> Tuple[Set[int], bool]:
    """
    Получает список администраторов беседы через messages.getConversationMembers.
    Возвращает кортеж: (множество ID админов-пользователей, является_ли_бот_админом).
    """
    import time
    now = time.monotonic()
    if not force_refresh and peer_id in _CHAT_ADMINS_CACHE:
        ts, admins, bot_is_admin = _CHAT_ADMINS_CACHE[peer_id]
        if now - ts < CACHE_TTL:
            return admins, bot_is_admin

    try:
        response = await api_call_with_retry(
            api.messages.get_conversation_members,
            peer_id=peer_id
        )
        admins = set()
        bot_is_admin = False
        bot_member_id = -abs(group_id)

        for item in response.items:
            if item.is_admin or item.is_owner:
                if item.member_id > 0:
                    admins.add(item.member_id)
                elif item.member_id == bot_member_id:
                    bot_is_admin = True

        _CHAT_ADMINS_CACHE[peer_id] = (now, admins, bot_is_admin)
        return admins, bot_is_admin

    except VKAPIError as e:
        # Код 917: У бота нет прав администратора в этой беседе для просмотра участников
        if e.code == 917:
            logger.warning(f"Бот не имеет прав администратора в беседе {peer_id} (VK Error 917).")
        else:
            logger.error(f"Ошибка при получении участников беседы {peer_id}: {e}")
        return set(), False

async def delete_message_safe(api: API, peer_id: int, cmids: list[int]) -> bool:
    """
    Безопасное удаление сообщения в беседе для всех участников.
    В VK API v5.199+ при удалении в беседах используется conversation_message_ids + peer_id + delete_for_all=1.
    """
    try:
        await api_call_with_retry(
            api.messages.delete,
            peer_id=peer_id,
            cmids=cmids,
            delete_for_all=True
        )
        return True
    except VKAPIError as e:
        logger.debug(f"Не удалось удалить сообщение {cmids} в {peer_id}: {e}")
        return False

async def kick_user_safe(api: API, peer_id: int, user_id: int) -> Tuple[bool, str]:
    """
    Безопасное исключение пользователя из беседы через messages.removeChatUser.
    Обрабатывает выход юзера до бана и отсутствие прав у бота.
    """
    chat_id = peer_id - 2000000000
    if chat_id <= 0:
        return False, "Команда доступна только в беседах."
    try:
        await api_call_with_retry(
            api.messages.remove_chat_user,
            chat_id=chat_id,
            member_id=user_id
        )
        return True, "Успешно исключен."
    except VKAPIError as e:
        if e.code in (15, 925, 917):
            return False, "Недостаточно прав (бот не админ или цель является администратором ВК)."
        elif e.code == 935:
            return False, "Пользователь уже вышел из беседы."
        else:
            return False, f"Ошибка VK API ({e.code}): {e.description}"
