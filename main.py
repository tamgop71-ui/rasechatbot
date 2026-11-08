import sys
from loguru import logger
from vkbottle.bot import Bot, BotLabeler
from config import config
from database.db import db
from middlewares.context_middleware import ModerationMiddleware
from handlers.moderation import moderation_labeler
from handlers.events import events_labeler
from handlers.automod import automod_labeler

# Настройка логирования для консоли Bothost
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{message}</cyan>",
    level="INFO"
)

def create_bot() -> Bot:
    labeler = BotLabeler()
    labeler.message_view.register_middleware(ModerationMiddleware)

    labeler.load(events_labeler)
    labeler.load(moderation_labeler)
    labeler.load(automod_labeler)

    bot = Bot(token=config.vk_token, labeler=labeler)

    async def on_startup():
        logger.info("Запуск VK Бота Модератора (API v5.199+ | MySQL)...")
        await db.connect(config)

    async def on_shutdown():
        logger.info("Остановка бота, закрытие соединений с БД...")
        await db.close()

    bot.loop_wrapper.on_startup.append(on_startup())
    bot.loop_wrapper.on_shutdown.append(on_shutdown())
    return bot

if __name__ == "__main__":
    bot_instance = create_bot()
    bot_instance.run_forever()
