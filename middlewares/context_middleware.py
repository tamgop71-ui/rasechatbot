import time
import random
from collections import defaultdict, deque
from vkbottle import BaseMiddleware
from vkbottle.bot import Message
from config import config
from database.db import db
from utils.vk_helpers import get_vk_chat_admins, delete_message_safe

# Память для антифлуда (sliding window): {(peer_id, user_id): deque([timestamps])}
_FLOOD_TRACKER = defaultdict(lambda: deque(maxlen=10))
# Память для проверки повторяющихся сообщений: {(peer_id, user_id): (last_text, count)}
_REPEAT_TRACKER = {}

ROLE_LEVELS = {
    "user": 1,
    "mod": 2,
    "admin": 3,
    "owner": 4
}

class ModerationMiddleware(BaseMiddleware[Message]):
    """
    Единый pre-middleware для:
    1. Регистрации пользователя и беседы в PostgreSQL.
    2. Проверки активного мута (с автоудалением сообщения через messages.delete).
    3. Вычисления эффективной роли пользователя (OWNER_ID + админы ВК + роль из БД).
    4. Антиспам/антифлуд трекинга.
    """
    async def pre(self) -> None:
        msg: Message = self.event
        user_id = msg.from_id
        peer_id = msg.peer_id

        # Игнорируем сообщения от сообществ (отрицательный from_id)
        if user_id <= 0:
            self.stop("Сообщение от сообщества")
            return

        # 1. Регистрируем юзера и получаем настройки чата
        await db.ensure_user(user_id)
        is_chat = peer_id > 2000000000
        chat_settings = await db.ensure_chat(peer_id) if is_chat else {}

        # 2. Проверка активного мута в беседе
        if is_chat:
            active_mute = await db.get_active_mute(peer_id, user_id)
            if active_mute:
                # Удаляем сообщение мутнутого пользователя
                deleted = await delete_message_safe(msg.ctx_api, peer_id, [msg.conversation_message_id])
                if not active_mute.get("notified"):
                    await db.mark_mute_notified(peer_id, user_id)
                    exp = active_mute["expires_at"]
                    exp_str = exp.strftime("%d.%m.%Y %H:%M UTC") if exp else "навсегда"
                    warn_note = "" if deleted else "\n⚠️ (Выдайте боту права администратора для автоудаления сообщений!)"
                    await msg.answer(
                        f"🔇 [id{user_id}|Вы] находитесь в муте ({exp_str}). Причина: {active_mute['reason']}.{warn_note}"
                    )
                # Прерываем дальнейшую обработку хендлерами
                self.stop("Пользователь в муте")
                return

        # 3. Определение прав и ролей
        db_role = await db.get_role(peer_id, user_id) if is_chat else "user"
        vk_admins, bot_is_admin = (await get_vk_chat_admins(msg.ctx_api, peer_id, config.vk_group_id)) if is_chat else (set(), False)

        effective_role = db_role
        if user_id == config.owner_id:
            effective_role = "owner"
        elif user_id in vk_admins:
            effective_role = "admin"

        role_level = ROLE_LEVELS.get(effective_role, 1)

        # 4. Проверка флуда (только для обычных пользователей в беседах)
        is_flooding = False
        is_repeating = False
        if is_chat and chat_settings.get("antispam", True) and role_level < 2:
            now = time.monotonic()
            key = (peer_id, user_id)
            timestamps = _FLOOD_TRACKER[key]
            timestamps.append(now)

            # Если 5 сообщений за 4 секунды — считаем флудом
            if len(timestamps) >= 5 and (now - timestamps[-5]) < 4.0:
                is_flooding = True

            # Проверка одинаковых сообщений подряд (3 одинаковых текста)
            clean_text = (msg.text or "").strip().lower()
            if clean_text:
                last_text, rep_count = _REPEAT_TRACKER.get(key, ("", 0))
                if clean_text == last_text:
                    rep_count += 1
                else:
                    rep_count = 1
                _REPEAT_TRACKER[key] = (clean_text, rep_count)
                if rep_count >= 3:
                    is_repeating = True

        # Передаем контекст во все хендлеры
        self.send({
            "chat_settings": chat_settings,
            "user_role": effective_role,
            "role_level": role_level,
            "bot_is_admin": bot_is_admin,
            "is_flooding": is_flooding,
            "is_repeating": is_repeating,
            "is_chat": is_chat
        })
