from vkbottle.bot import BotLabeler, Message
from database.db import db
from utils.vk_helpers import kick_user_safe
from utils.action_logger import log_moderation_action

events_labeler = BotLabeler()

@events_labeler.raw_event("message_new", Message)
async def handle_chat_events(message: Message):
    """
    Обработчик сервисных событий беседы (action):
    - chat_invite_user / chat_invite_user_by_link (вход участника -> проверка автобана или приветствие)
    - chat_kick_user (выход или исключение участника)
    """
    if not message.action or message.peer_id <= 2000000000:
        return

    action_type = str(message.action.type)
    # В зависимости от версии схемы vkbottle тип может приходить как строка или Enum
    if "chat_invite_user" in action_type:
        member_id = message.action.member_id or message.from_id
        if not member_id or member_id <= 0:
            return

        await db.ensure_user(member_id)
        settings = await db.get_settings(message.peer_id)

        # 1. Проверяем, находится ли вошедший пользователь в черном списке (бане)
        ban_record = await db.is_banned(message.peer_id, member_id)
        if ban_record:
            ok, info = await kick_user_safe(message.ctx_api, message.peer_id, member_id)
            await message.answer(
                f"🚫 [id{member_id}|Пользователь] находится в черном списке беседы (Причина: {ban_record['reason']}) и был автоматически исключен ({info})."
            )
            await log_moderation_action(
                message.ctx_api, message.peer_id, 0, member_id,
                "AUTOBAN_ON_JOIN", f"Причина бана: {ban_record['reason']} ({info})"
            )
            return

        # 2. Приветствие нового участника
        welcome_tpl = settings.get("welcome_text")
        if welcome_tpl:
            mention = f"[id{member_id}|участник]"
            text = welcome_tpl.replace("{mention}", mention)
            await message.answer(text)
