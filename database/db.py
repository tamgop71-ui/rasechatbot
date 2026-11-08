import os
import aiomysql
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from loguru import logger
from config import Config

DEFAULT_WELCOME = "Добро пожаловать в беседу, {mention}! Соблюдайте правила."
DEFAULT_WHITELIST = "vk.com,wikipedia.org,github.com"

class Database:
    def __init__(self):
        self.pool: Optional[aiomysql.Pool] = None

    async def connect(self, cfg: Config):
        """Инициализация пула соединений к MySQL (с поддержкой авто-переподключения)."""
        logger.info(f"Подключение к базе данных MySQL ({cfg.db_host}:{cfg.db_port}, db={cfg.db_name})...")
        self.pool = await aiomysql.create_pool(
            host=cfg.db_host,
            port=cfg.db_port,
            user=cfg.db_user,
            password=cfg.db_pass,
            db=cfg.db_name,
            charset="utf8mb4",
            autocommit=True,
            minsize=1,
            maxsize=5,
            connect_timeout=15
        )
        await self.init_schema()
        logger.info("База данных MySQL успешно подключена и инициализирована.")

    async def close(self):
        if self.pool:
            self.pool.close()
            await self.pool.wait_closed()
            logger.info("Соединение с базой данных MySQL закрыто.")

    async def init_schema(self):
        """Применение SQL-миграции MySQL при старте."""
        schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
        with open(schema_path, "r", encoding="utf-8") as f:
            sql_script = f.read()

        statements = [s.strip() for s in sql_script.split(";") if s.strip()]
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                for stmt in statements:
                    await cur.execute(stmt)

    # --- ПОЛЬЗОВАТЕЛИ И БЕСЕДЫ ---
    async def ensure_user(self, user_id: int, first_name: str = "Пользователь", last_name: str = ""):
        query = """
        INSERT INTO users (user_id, first_name, last_name)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE
            first_name = IF(first_name = 'Пользователь', VALUES(first_name), first_name),
            last_name = IF(last_name = '', VALUES(last_name), last_name)
        """
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, (user_id, first_name, last_name))

    async def ensure_chat(self, peer_id: int, title: str = "Беседа") -> Dict[str, Any]:
        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    """
                    INSERT INTO chats (peer_id, title, messages_count)
                    VALUES (%s, %s, 1)
                    ON DUPLICATE KEY UPDATE messages_count = messages_count + 1
                    """,
                    (peer_id, title)
                )
                await cur.execute(
                    """
                    INSERT IGNORE INTO settings (peer_id, welcome_text, whitelist_domains)
                    VALUES (%s, %s, %s)
                    """,
                    (peer_id, DEFAULT_WELCOME, DEFAULT_WHITELIST)
                )
                await cur.execute("SELECT * FROM settings WHERE peer_id = %s", (peer_id,))
                row = await cur.fetchone()
                return dict(row) if row else {}

    async def get_settings(self, peer_id: int) -> Dict[str, Any]:
        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute("SELECT * FROM settings WHERE peer_id = %s", (peer_id,))
                row = await cur.fetchone()
                if not row:
                    return await self.ensure_chat(peer_id)
                return dict(row)

    async def update_setting(self, peer_id: int, column: str, value: Any):
        allowed_columns = {
            "warn_limit", "warn_punishment", "antimat",
            "antispam", "antilinks", "antiinvite", "welcome_text", "whitelist_domains"
        }
        if column not in allowed_columns:
            raise ValueError(f"Недопустимая настройка: {column}")
        if isinstance(value, bool):
            value = 1 if value else 0
        query = f"UPDATE settings SET {column} = %s WHERE peer_id = %s"
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, (value, peer_id))

    # --- РОЛИ ---
    async def get_role(self, peer_id: int, user_id: int) -> str:
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT role FROM roles WHERE peer_id = %s AND user_id = %s",
                    (peer_id, user_id)
                )
                row = await cur.fetchone()
                return row[0] if row else "user"

    async def set_role(self, peer_id: int, user_id: int, role: str):
        await self.ensure_user(user_id)
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO roles (peer_id, user_id, role)
                    VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE role = VALUES(role), updated_at = CURRENT_TIMESTAMP
                    """,
                    (peer_id, user_id, role)
                )

    # --- МУТЫ ---
    async def add_mute(self, peer_id: int, user_id: int, admin_id: int, reason: str, expires_at: Optional[datetime]):
        await self.ensure_user(user_id)
        # Приводим UTC datetime к naive UTC для хранения в MySQL DATETIME
        exp_naive = expires_at.astimezone(timezone.utc).replace(tzinfo=None) if expires_at else None
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO mutes (peer_id, user_id, admin_id, reason, expires_at, notified)
                    VALUES (%s, %s, %s, %s, %s, 0)
                    ON DUPLICATE KEY UPDATE
                        admin_id = VALUES(admin_id),
                        reason = VALUES(reason),
                        expires_at = VALUES(expires_at),
                        notified = 0,
                        created_at = CURRENT_TIMESTAMP
                    """,
                    (peer_id, user_id, admin_id, reason, exp_naive)
                )

    async def remove_mute(self, peer_id: int, user_id: int) -> bool:
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("DELETE FROM mutes WHERE peer_id = %s AND user_id = %s", (peer_id, user_id))
                return cur.rowcount > 0

    async def get_active_mute(self, peer_id: int, user_id: int) -> Optional[Dict[str, Any]]:
        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT * FROM mutes WHERE peer_id = %s AND user_id = %s",
                    (peer_id, user_id)
                )
                row = await cur.fetchone()
                if not row:
                    return None
                now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
                if row["expires_at"] is not None and row["expires_at"] <= now_naive:
                    await cur.execute("DELETE FROM mutes WHERE peer_id = %s AND user_id = %s", (peer_id, user_id))
                    return None
                return dict(row)

    async def mark_mute_notified(self, peer_id: int, user_id: int):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "UPDATE mutes SET notified = 1 WHERE peer_id = %s AND user_id = %s",
                    (peer_id, user_id)
                )

    # --- БАНЫ ---
    async def add_ban(self, peer_id: int, user_id: int, admin_id: int, reason: str):
        await self.ensure_user(user_id)
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO bans (peer_id, user_id, admin_id, reason)
                    VALUES (%s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        admin_id = VALUES(admin_id),
                        reason = VALUES(reason),
                        created_at = CURRENT_TIMESTAMP
                    """,
                    (peer_id, user_id, admin_id, reason)
                )

    async def remove_ban(self, peer_id: int, user_id: int) -> bool:
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("DELETE FROM bans WHERE peer_id = %s AND user_id = %s", (peer_id, user_id))
                return cur.rowcount > 0

    async def is_banned(self, peer_id: int, user_id: int) -> Optional[Dict[str, Any]]:
        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute("SELECT * FROM bans WHERE peer_id = %s AND user_id = %s", (peer_id, user_id))
                row = await cur.fetchone()
                return dict(row) if row else None

    # --- ВАРНЫ ---
    async def add_warn(self, peer_id: int, user_id: int, admin_id: int, reason: str) -> int:
        await self.ensure_user(user_id)
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO warns (peer_id, user_id, admin_id, reason, is_active) VALUES (%s, %s, %s, %s, 1)",
                    (peer_id, user_id, admin_id, reason)
                )
                await cur.execute(
                    "SELECT COUNT(*) FROM warns WHERE peer_id = %s AND user_id = %s AND is_active = 1",
                    (peer_id, user_id)
                )
                row = await cur.fetchone()
                return int(row[0]) if row else 1

    async def remove_last_warn(self, peer_id: int, user_id: int) -> bool:
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT id FROM warns 
                    WHERE peer_id = %s AND user_id = %s AND is_active = 1
                    ORDER BY created_at DESC, id DESC LIMIT 1
                    """,
                    (peer_id, user_id)
                )
                row = await cur.fetchone()
                if not row:
                    return False
                await cur.execute("UPDATE warns SET is_active = 0 WHERE id = %s", (row[0],))
                return True

    async def clear_warns(self, peer_id: int, user_id: int):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "UPDATE warns SET is_active = 0 WHERE peer_id = %s AND user_id = %s",
                    (peer_id, user_id)
                )

    async def get_warns(self, peer_id: int, user_id: int) -> List[Dict[str, Any]]:
        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    """
                    SELECT id, admin_id, reason, created_at FROM warns
                    WHERE peer_id = %s AND user_id = %s AND is_active = 1
                    ORDER BY created_at ASC, id ASC
                    """,
                    (peer_id, user_id)
                )
                rows = await cur.fetchall()
                return [dict(r) for r in rows]

    # --- СТАТИСТИКА И ЛОГИ ---
    async def log_action(self, peer_id: int, actor_id: int, target_id: Optional[int], action: str, details: str = ""):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO logs (peer_id, actor_id, target_id, action, details) VALUES (%s, %s, %s, %s, %s)",
                    (peer_id, actor_id, target_id, action, details)
                )

    async def get_chat_stats(self, peer_id: int) -> Dict[str, Any]:
        now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute("SELECT messages_count FROM chats WHERE peer_id = %s", (peer_id,))
                r_msg = await cur.fetchone()
                messages_count = r_msg["messages_count"] if r_msg else 0

                await cur.execute("SELECT COUNT(*) AS cnt FROM warns WHERE peer_id = %s AND is_active = 1", (peer_id,))
                active_warns = (await cur.fetchone())["cnt"]

                await cur.execute("SELECT COUNT(*) AS cnt FROM bans WHERE peer_id = %s", (peer_id,))
                bans_count = (await cur.fetchone())["cnt"]

                await cur.execute(
                    "SELECT COUNT(*) AS cnt FROM mutes WHERE peer_id = %s AND (expires_at IS NULL OR expires_at > %s)",
                    (peer_id, now_naive)
                )
                mutes_count = (await cur.fetchone())["cnt"]

                await cur.execute("SELECT user_id, role FROM roles WHERE peer_id = %s AND role != 'user'", (peer_id,))
                staff = await cur.fetchall()

                return {
                    "messages_count": messages_count,
                    "active_warns": active_warns,
                    "bans_count": bans_count,
                    "mutes_count": mutes_count,
                    "staff": [dict(r) for r in staff]
                }

db = Database()
