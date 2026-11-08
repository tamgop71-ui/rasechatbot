from vkbottle.bot import BotLabeler, Message
from config import config
from database.db import db
from utils.mention_parser import extract_target_and_args
from utils.time_parser import parse_mute_time
from utils.vk_helpers import kick_user_safe, get_vk_chat_admins
from utils.action_logger import log_moderation_action

moderation_labeler = BotLabeler()

async def check_target_hierarchy(message: Message, target_id: int, actor_level: int) -> bool:
    """Проверяет, можно ли применить наказание к target_id."""
    if target_id == message.from_id:
        await message.answer("❌ Нельзя применить это действие к самому себе.")
        return False
    if target_id <= 0:
        await message.answer("❌ Действие применимо только к пользователям.")
        return False
    if target_id == config.owner_id:
        await message.answer("❌ Нельзя применить наказание к владельцу бота.")
        return False

    vk_admins, _ = await get_vk_chat_admins(message.ctx_api, message.peer_id, config.vk_group_id)
    target_db_role = await db.get_role(message.peer_id, target_id)
    target_level = 3 if target_id in vk_admins else (3 if target_db_role == "admin" else (2 if target_db_role == "mod" else 1))

    if target_level >= actor_level and message.from_id != config.owner_id:
        await message.answer("❌ Недостаточно прав: цель имеет равную или более высокую роль.")
        return False
    return True

async def execute_auto_punishment(message: Message, target_id: int, punishment: str, reason: str):
    """Выполняет автонаказание при достижении лимита варнов."""
    peer_id = message.peer_id
    await db.clear_warns(peer_id, target_id)

    if punishment == "kick":
        ok, info = await kick_user_safe(message.ctx_api, peer_id, target_id)
        await message.answer(f"🔨 Лимит предупреждений! [id{target_id}|Пользователь] исключен из беседы ({info}).")
    elif punishment == "mute":
        expires_at, label, _ = parse_mute_time("2h")
        await db.add_mute(peer_id, target_id, message.from_id, f"Автомут: {reason}", expires_at)
        await message.answer(f"🔇 Лимит предупреждений! [id{target_id}|Пользователь] получил мут на {label}.")
    else:  # ban по умолчанию
        await db.add_ban(peer_id, target_id, message.from_id, f"Автобан по лимиту варнов: {reason}")
        ok, info = await kick_user_safe(message.ctx_api, peer_id, target_id)
        await message.answer(f"🚫 Лимит предупреждений! [id{target_id}|Пользователь] забанен ({info}).")

    await log_moderation_action(
        message.ctx_api, peer_id, message.from_id, target_id,
        f"AUTO_{punishment.upper()}", f"Достигнут лимит варнов ({reason})"
    )

@moderation_labeler.message(text=["/kick", "/kick <args>"])
async def cmd_kick(message: Message, role_level: int = 1, is_chat: bool = False, **kwargs):
    if not is_chat:
        return await message.answer("ℹ️ Команда /kick работает только в беседах.")
    if role_level < 2:
        return await message.answer("⛔ Команда доступна только модераторам и администраторам.")

    target_id, rest = await extract_target_and_args(message, message.ctx_api)
    if not target_id:
        return await message.answer("Использование: /kick @user [причина] (или ответом на сообщение)")

    if not await check_target_hierarchy(message, target_id, role_level):
        return

    reason = " ".join(rest) if rest else "Без указания причины"
    ok, info = await kick_user_safe(message.ctx_api, message.peer_id, target_id)
    if ok:
        await message.answer(f"👢 [id{target_id}|Пользователь] исключен из беседы.\nПричина: {reason}")
        await log_moderation_action(message.ctx_api, message.peer_id, message.from_id, target_id, "KICK", reason)
    else:
        await message.answer(f"⚠️ Не удалось исключить [id{target_id}|пользователя]: {info}")

@moderation_labeler.message(text=["/ban", "/ban <args>"])
async def cmd_ban(message: Message, role_level: int = 1, is_chat: bool = False, **kwargs):
    if not is_chat:
        return await message.answer("ℹ️ Команда /ban работает только в беседах.")
    if role_level < 2:
        return await message.answer("⛔ Команда доступна только модераторам и администраторам.")

    target_id, rest = await extract_target_and_args(message, message.ctx_api)
    if not target_id:
        return await message.answer("Использование: /ban @user [причина] (или ответом на сообщение)")

    if not await check_target_hierarchy(message, target_id, role_level):
        return

    reason = " ".join(rest) if rest else "Нарушение правил"
    # Сначала пишем бан в БД (даже если юзер уже вышел из чата — автобан сработает при возврате)
    await db.add_ban(message.peer_id, target_id, message.from_id, reason)
    ok, info = await kick_user_safe(message.ctx_api, message.peer_id, target_id)

    status_note = "и исключен из чата" if ok else f"(статус кика: {info})"
    await message.answer(f"🚫 [id{target_id}|Пользователь] занесен в черный список беседы {status_note}.\nПричина: {reason}")
    await log_moderation_action(message.ctx_api, message.peer_id, message.from_id, target_id, "BAN", reason)

@moderation_labeler.message(text=["/unban", "/unban <args>"])
async def cmd_unban(message: Message, role_level: int = 1, is_chat: bool = False, **kwargs):
    if not is_chat:
        return await message.answer("ℹ️ Команда /unban работает только в беседах.")
    if role_level < 2:
        return await message.answer("⛔ Недостаточно прав.")

    target_id, _ = await extract_target_and_args(message, message.ctx_api)
    if not target_id:
        return await message.answer("Использование: /unban @user")

    removed = await db.remove_ban(message.peer_id, target_id)
    if removed:
        await message.answer(f"✅ С [id{target_id}|пользователя] снят бан в беседе.")
        await log_moderation_action(message.ctx_api, message.peer_id, message.from_id, target_id, "UNBAN", "Снятие бана")
    else:
        await message.answer(f"ℹ️ [id{target_id}|Пользователь] не числится в бане.")

@moderation_labeler.message(text=["/mute", "/mute <args>"])
async def cmd_mute(message: Message, role_level: int = 1, is_chat: bool = False, bot_is_admin: bool = False, **kwargs):
    if not is_chat:
        return await message.answer("ℹ️ Команда /mute работает только в беседах.")
    if role_level < 2:
        return await message.answer("⛔ Команда доступна только модераторам и администраторам.")

    target_id, rest = await extract_target_and_args(message, message.ctx_api)
    if not target_id:
        return await message.answer("Использование: /mute @user [10m|2h|1d|perm] [причина]")

    if not await check_target_hierarchy(message, target_id, role_level):
        return

    time_token = rest[0] if rest else "30m"
    expires_at, time_label, parsed_ok = parse_mute_time(time_token)
    if parsed_ok:
        reason = " ".join(rest[1:]) if len(rest) > 1 else "Нарушение правил"
    else:
        expires_at, time_label, _ = parse_mute_time("30m")
        reason = " ".join(rest) if rest else "Нарушение правил"

    await db.add_mute(message.peer_id, target_id, message.from_id, reason, expires_at)
    admin_warn = "" if bot_is_admin else "\n⚠️ Внимание: бот не является администратором беседы, поэтому не сможет удалять сообщения!"
    await message.answer(
        f"🔇 [id{target_id}|Пользователю] выдан мут ({time_label}).\nПричина: {reason}{admin_warn}"
    )
    await log_moderation_action(
        message.ctx_api, message.peer_id, message.from_id, target_id,
        "MUTE", f"Срок: {time_label}, причина: {reason}"
    )

@moderation_labeler.message(text=["/unmute", "/unmute <args>"])
async def cmd_unmute(message: Message, role_level: int = 1, is_chat: bool = False, **kwargs):
    if not is_chat:
        return await message.answer("ℹ️ Команда /unmute работает только в беседах.")
    if role_level < 2:
        return await message.answer("⛔ Недостаточно прав.")

    target_id, _ = await extract_target_and_args(message, message.ctx_api)
    if not target_id:
        return await message.answer("Использование: /unmute @user")

    removed = await db.remove_mute(message.peer_id, target_id)
    if removed:
        await message.answer(f"🔊 С [id{target_id}|пользователя] снят мут.")
        await log_moderation_action(message.ctx_api, message.peer_id, message.from_id, target_id, "UNMUTE", "Снятие мута")
    else:
        await message.answer(f"ℹ️ У [id{target_id}|пользователя] нет активного мута.")

@moderation_labeler.message(text=["/warn", "/warn <args>"])
async def cmd_warn(message: Message, role_level: int = 1, is_chat: bool = False, chat_settings: dict = None, **kwargs):
    if not is_chat:
        return await message.answer("ℹ️ Команда /warn работает только в беседах.")
    if role_level < 2:
        return await message.answer("⛔ Недостаточно прав.")

    target_id, rest = await extract_target_and_args(message, message.ctx_api)
    if not target_id:
        return await message.answer("Использование: /warn @user [причина]")

    if not await check_target_hierarchy(message, target_id, role_level):
        return

    reason = " ".join(rest) if rest else "Нарушение правил"
    count = await db.add_warn(message.peer_id, target_id, message.from_id, reason)
    limit = (chat_settings or {}).get("warn_limit", 3)
    punishment = (chat_settings or {}).get("warn_punishment", "ban")

    await message.answer(f"⚠️ [id{target_id}|Пользователь] получил предупреждение ({count}/{limit}).\nПричина: {reason}")
    await log_moderation_action(
        message.ctx_api, message.peer_id, message.from_id, target_id,
        "WARN", f"{count}/{limit}: {reason}"
    )

    if count >= limit:
        await execute_auto_punishment(message, target_id, punishment, reason)

@moderation_labeler.message(text=["/unwarn", "/unwarn <args>"])
async def cmd_unwarn(message: Message, role_level: int = 1, is_chat: bool = False, **kwargs):
    if not is_chat:
        return await message.answer("ℹ️ Команда /unwarn работает только в беседах.")
    if role_level < 2:
        return await message.answer("⛔ Недостаточно прав.")

    target_id, _ = await extract_target_and_args(message, message.ctx_api)
    if not target_id:
        return await message.answer("Использование: /unwarn @user")

    removed = await db.remove_last_warn(message.peer_id, target_id)
    if removed:
        warns = await db.get_warns(message.peer_id, target_id)
        await message.answer(f"✅ С [id{target_id}|пользователя] снято одно предупреждение (осталось: {len(warns)}).")
        await log_moderation_action(message.ctx_api, message.peer_id, message.from_id, target_id, "UNWARN", "Снят 1 варн")
    else:
        await message.answer(f"ℹ️ У [id{target_id}|пользователя] нет активных предупреждений.")

@moderation_labeler.message(text=["/warns", "/warns <args>"])
async def cmd_warns(message: Message, is_chat: bool = False, chat_settings: dict = None, **kwargs):
    if not is_chat:
        return await message.answer("ℹ️ Команда /warns работает только в беседах.")

    target_id, _ = await extract_target_and_args(message, message.ctx_api)
    if not target_id:
        target_id = message.from_id

    warns = await db.get_warns(message.peer_id, target_id)
    limit = (chat_settings or {}).get("warn_limit", 3)
    if not warns:
        return await message.answer(f"✨ У [id{target_id}|пользователя] нет активных предупреждений (0/{limit}).")

    lines = [f"📋 Предупреждения [id{target_id}|пользователя] ({len(warns)}/{limit}):"]
    for idx, w in enumerate(warns, 1):
        dt = w["created_at"].strftime("%d.%m.%Y %H:%M")
        lines.append(f"{idx}. [{dt}] От [id{w['admin_id']}|модератора] — {w['reason']}")
    await message.answer("\n".join(lines))

@moderation_labeler.message(text=["/role", "/role <args>"])
async def cmd_role(message: Message, role_level: int = 1, is_chat: bool = False, **kwargs):
    if not is_chat:
        return await message.answer("ℹ️ Команда /role работает только в беседах.")
    if role_level < 3:
        return await message.answer("⛔ Управление ролями доступно только администраторам беседы.")

    target_id, rest = await extract_target_and_args(message, message.ctx_api)
    if not target_id or not rest:
        return await message.answer("Использование: /role @user [admin|mod|user]")

    new_role = rest[0].lower().strip()
    if new_role not in ("admin", "mod", "user"):
        return await message.answer("❌ Роль должна быть одной из: admin, mod, user.")

    await db.set_role(message.peer_id, target_id, new_role)
    await message.answer(f"🎖 [id{target_id}|Пользователю] установлена роль «{new_role}» в боте.")
    await log_moderation_action(message.ctx_api, message.peer_id, message.from_id, target_id, "SET_ROLE", f"Роль: {new_role}")

@moderation_labeler.message(text=["/settings", "/settings <args>"])
async def cmd_settings(message: Message, role_level: int = 1, is_chat: bool = False, **kwargs):
    # Поддержка работы как в беседе, так и в ЛС от владельца/админа
    parts = message.text.strip().split()
    args = parts[1:]

    target_peer_id = message.peer_id
    if not is_chat:
        if message.from_id != config.owner_id and role_level < 3:
            return await message.answer("⛔ В ЛС команда доступна только администраторам. Укажите ID чата: /settings <chat_id> [ключ] [значение]")
        if not args or not args[0].isdigit():
            return await message.answer("ℹ️ В ЛС укажите номер беседы: /settings <chat_id> [ключ] [значение]\nПример: /settings 1 antimat on")
        chat_num = int(args[0])
        target_peer_id = chat_num if chat_num > 2000000000 else 2000000000 + chat_num
        args = args[1:]
    else:
        if role_level < 3:
            return await message.answer("⛔ Настройки доступны только администраторам беседы.")

    settings = await db.get_settings(target_peer_id)

    if not args:
        flag = lambda v: "✅ Вкл" if v else "❌ Выкл"
        text = (
            f"⚙️ Настройки беседы (peer: {target_peer_id}):\n"
            f"• Порог варнов (warn_limit): {settings['warn_limit']}\n"
            f"• Автонаказание (warn_punishment): {settings['warn_punishment']}\n"
            f"• Антимат (antimat): {flag(settings['antimat'])}\n"
            f"• Антиспам (antispam): {flag(settings['antispam'])}\n"
            f"• Антиссылки (antilinks): {flag(settings['antilinks'])}\n"
            f"• Анти-инвайты (antiinvite): {flag(settings['antiinvite'])}\n"
            f"• Белый список доменов (whitelist): {settings['whitelist_domains']}\n"
            f"• Приветствие (welcome): {settings['welcome_text']}\n\n"
            f"Для изменения: /settings <ключ> <значение>\n"
            f"Примеры:\n"
            f"/settings antimat off\n"
            f"/settings warn_limit 5\n"
            f"/settings warn_punishment mute\n"
            f"/settings welcome Привет, {{mention}}!"
        )
        return await message.answer(text)

    key = args[0].lower()
    val_raw = " ".join(args[1:]).strip()
    if not val_raw:
        return await message.answer("❌ Укажите новое значение параметра.")

    bool_map = {"on": True, "true": True, "1": True, "вкл": True, "off": False, "false": False, "0": False, "выкл": False}

    if key in ("antimat", "antispam", "antilinks", "antiinvite"):
        if val_raw.lower() not in bool_map:
            return await message.answer("❌ Используйте on / off.")
        await db.update_setting(target_peer_id, key, bool_map[val_raw.lower()])
    elif key == "warn_limit":
        if not val_raw.isdigit() or not (1 <= int(val_raw) <= 20):
            return await message.answer("❌ Укажите число от 1 до 20.")
        await db.update_setting(target_peer_id, "warn_limit", int(val_raw))
    elif key == "warn_punishment":
        if val_raw.lower() not in ("kick", "ban", "mute"):
            return await message.answer("❌ Допустимые значения: kick, ban, mute.")
        await db.update_setting(target_peer_id, "warn_punishment", val_raw.lower())
    elif key in ("welcome", "welcome_text"):
        await db.update_setting(target_peer_id, "welcome_text", val_raw)
    elif key in ("whitelist", "whitelist_domains"):
        await db.update_setting(target_peer_id, "whitelist_domains", val_raw.lower())
    else:
        return await message.answer("❌ Неизвестный параметр. Доступны: antimat, antispam, antilinks, antiinvite, warn_limit, warn_punishment, welcome, whitelist.")

    await message.answer(f"✅ Настройка «{key}» для чата {target_peer_id} обновлена!")
    await log_moderation_action(message.ctx_api, target_peer_id, message.from_id, None, "UPDATE_SETTING", f"{key} = {val_raw}")

@moderation_labeler.message(text=["/stats", "/stats <args>"])
async def cmd_stats(message: Message, is_chat: bool = False, **kwargs):
    parts = message.text.strip().split()
    target_peer_id = message.peer_id
    if not is_chat:
        if len(parts) < 2 or not parts[1].isdigit():
            return await message.answer("ℹ️ В ЛС укажите ID чата: /stats <chat_id>")
        c_id = int(parts[1])
        target_peer_id = c_id if c_id > 2000000000 else 2000000000 + c_id

    stats = await db.get_chat_stats(target_peer_id)
    staff_lines = [f"[id{s['user_id']}|{s['role'].upper()}]" for s in stats["staff"]]
    staff_str = ", ".join(staff_lines) if staff_lines else "Не назначены"

    text = (
        f"📊 Статистика беседы (peer: {target_peer_id}):\n"
        f"💬 Всего сообщений обработано: {stats['messages_count']}\n"
        f"⚠️ Активных предупреждений: {stats['active_warns']}\n"
        f"🔇 Активных мутов: {stats['mutes_count']}\n"
        f"🚫 Забанено пользователей: {stats['bans_count']}\n"
        f"👮 Роли в боте: {staff_str}"
    )
    await message.answer(text)
