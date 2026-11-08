import re
from typing import Optional, Tuple, List
from vkbottle.bot import Message
from vkbottle import API

# Паттерн нативного упоминания ВК: [id12345|Имя]
VK_MENTION_RE = re.compile(r"\[(?:id|club)(\d+)\|[^\]]+\]")
# Паттерн ссылки или @screen_name или id12345
SCREEN_NAME_RE = re.compile(r"^(?:https?://vk\.com/)?@?([a-zA-Z0-9_\.]+)$")

async def extract_target_and_args(message: Message, api: API) -> Tuple[Optional[int], List[str]]:
    """
    Универсальный парсер цели команды и оставшихся аргументов.
    Поддерживает:
    1. Ответ на сообщение (reply_message) или пересланные сообщения (fwd_messages)
    2. Упоминание [id123|@user]
    3. Прямой ввод id12345, числа 12345, ссылки vk.com/durov или @screen_name
    """
    parts = message.text.strip().split()
    args = parts[1:] if len(parts) > 1 else []

    # 1. Проверяем reply_message
    if message.reply_message:
        return message.reply_message.from_id, args

    # 2. Проверяем fwd_messages
    if message.fwd_messages:
        return message.fwd_messages[0].from_id, args

    if not args:
        return None, []

    first_arg = args[0]
    remaining_args = args[1:]

    # 3. Проверяем формат [id12345|Имя]
    mention_match = VK_MENTION_RE.search(first_arg)
    if mention_match:
        return int(mention_match.group(1)), remaining_args

    # 4. Проверяем чистое число или id12345
    if first_arg.isdigit():
        return int(first_arg), remaining_args
    if first_arg.lower().startswith("id") and first_arg[2:].isdigit():
        return int(first_arg[2:]), remaining_args

    # 5. Проверяем @screen_name или vk.com/screen_name через utils.resolveScreenName
    sn_match = SCREEN_NAME_RE.match(first_arg)
    if sn_match:
        screen_name = sn_match.group(1)
        try:
            resolved = await api.utils.resolve_screen_name(screen_name=screen_name)
            if resolved and resolved.object_id and str(resolved.type) in ("user", "UtilsDomainResolvedType.USER"):
                return int(resolved.object_id), remaining_args
        except Exception:
            pass

    return None, args
