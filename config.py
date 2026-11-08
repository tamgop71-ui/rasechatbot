import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

# =====================================================================
# ПРЯМАЯ НАСТРОЙКА БОТА И БАЗЫ ДАННЫХ MYSQL (ВПИШИТЕ ДАННЫЕ СЮДА)
# =====================================================================

# 1. Настройки ВКонтакте
VK_TOKEN = "vk1.a.ВАШ_ТОКЕН_ГРУППЫ"   # Токен сообщества ВК
VK_GROUP_ID = 123456789               # ID группы (число без минуса)
LOG_CHAT_ID = 2000000001              # Peer ID беседы для логов (например 2000000001) или ID юзера
OWNER_ID = 12345678                   # Ваш личный цифровой VK ID (главный админ)

# 2. Данные для подключения к базе данных MySQL (порт 3306)
# ВАЖНО: Если бот запускается на Bothost, а база находится на внешнем хостинге (например, Reg.ru / ISPmanager),
# замените "127.0.0.1" на внешний IP-адрес или домен вашего хостинга (например, "forum-raserussia.online" или IP сервера),
# так как внутри контейнера Bothost адрес 127.0.0.1 указывает на сам контейнер Bothost!
DB_HOST = "127.0.0.1"                 # IP или домен сервера MySQL
DB_PORT = 3306                        # Порт MySQL
DB_USER = "u3715066_vkbot"            # Имя пользователя БД (обычно совпадает с именем БД в ISPmanager)
DB_PASS = "vkbottamgop123"            # Пароль БД
DB_NAME = "u3715066_vkbot"            # Имя базы данных

# =====================================================================

@dataclass
class Config:
    vk_token: str
    vk_group_id: int
    log_chat_id: int
    owner_id: int
    db_host: str
    db_port: int
    db_user: str
    db_pass: str
    db_name: str

def load_config() -> Config:
    return Config(
        vk_token=os.getenv("VK_TOKEN") or VK_TOKEN,
        vk_group_id=int(os.getenv("VK_GROUP_ID") or VK_GROUP_ID),
        log_chat_id=int(os.getenv("LOG_CHAT_ID") or LOG_CHAT_ID),
        owner_id=int(os.getenv("OWNER_ID") or OWNER_ID),
        db_host=os.getenv("DB_HOST") or DB_HOST,
        db_port=int(os.getenv("DB_PORT") or DB_PORT),
        db_user=os.getenv("DB_USER") or DB_USER,
        db_pass=os.getenv("DB_PASS") or DB_PASS,
        db_name=os.getenv("DB_NAME") or DB_NAME,
    )

config = load_config()
