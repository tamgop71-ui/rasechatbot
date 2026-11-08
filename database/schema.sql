-- Схема базы данных MySQL для VK Бота Модератора (API v5.199+)

CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    first_name VARCHAR(128) NOT NULL DEFAULT 'Пользователь',
    last_name VARCHAR(128) NOT NULL DEFAULT '',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS chats (
    peer_id BIGINT PRIMARY KEY,
    title VARCHAR(255) NOT NULL DEFAULT 'Беседа',
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    messages_count BIGINT NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS settings (
    peer_id BIGINT PRIMARY KEY,
    warn_limit SMALLINT NOT NULL DEFAULT 3,
    warn_punishment VARCHAR(16) NOT NULL DEFAULT 'ban',
    antimat TINYINT(1) NOT NULL DEFAULT 1,
    antispam TINYINT(1) NOT NULL DEFAULT 1,
    antilinks TINYINT(1) NOT NULL DEFAULT 1,
    antiinvite TINYINT(1) NOT NULL DEFAULT 1,
    welcome_text TEXT NULL,
    whitelist_domains TEXT NULL,
    CONSTRAINT fk_settings_chat FOREIGN KEY (peer_id) REFERENCES chats(peer_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS roles (
    peer_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    role VARCHAR(16) NOT NULL DEFAULT 'user',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (peer_id, user_id),
    INDEX idx_roles_peer_role (peer_id, role),
    CONSTRAINT fk_roles_chat FOREIGN KEY (peer_id) REFERENCES chats(peer_id) ON DELETE CASCADE,
    CONSTRAINT fk_roles_user FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS warns (
    id INT AUTO_INCREMENT PRIMARY KEY,
    peer_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    admin_id BIGINT NOT NULL,
    reason TEXT NOT NULL,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_warns_active (peer_id, user_id, is_active),
    CONSTRAINT fk_warns_chat FOREIGN KEY (peer_id) REFERENCES chats(peer_id) ON DELETE CASCADE,
    CONSTRAINT fk_warns_user FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS bans (
    peer_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    admin_id BIGINT NOT NULL,
    reason TEXT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (peer_id, user_id),
    CONSTRAINT fk_bans_chat FOREIGN KEY (peer_id) REFERENCES chats(peer_id) ON DELETE CASCADE,
    CONSTRAINT fk_bans_user FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS mutes (
    peer_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    admin_id BIGINT NOT NULL,
    reason TEXT NOT NULL,
    expires_at DATETIME NULL,
    notified TINYINT(1) NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (peer_id, user_id),
    INDEX idx_mutes_expires (expires_at),
    CONSTRAINT fk_mutes_chat FOREIGN KEY (peer_id) REFERENCES chats(peer_id) ON DELETE CASCADE,
    CONSTRAINT fk_mutes_user FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS logs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    peer_id BIGINT NOT NULL,
    actor_id BIGINT NOT NULL,
    target_id BIGINT NULL,
    action VARCHAR(64) NOT NULL,
    details TEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_logs_peer_created (peer_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
