# VK Moderator Bot (API v5.199+ | vkbottle | PostgreSQL)

Асинхронный бот для модерации бесед ВКонтакте, адаптированный для деплоя на **Bothost** через GitHub.

## Быстрая настройка через файл `config.py`
Откройте файл `config.py` и впишите свои данные в верхнем блоке:
- `VK_TOKEN`, `VK_GROUP_ID`, `LOG_CHAT_ID`, `OWNER_ID`
- Данные вашей базы PostgreSQL: `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASS`, `DB_NAME`

После этого залейте файлы в свой **приватный (Private)** репозиторий GitHub и подключите его на Bothost. Команда запуска: `python main.py`.
