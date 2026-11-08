import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

TIME_PATTERN = re.compile(r"^(\d+)([smhdмчдс])$", re.IGNORECASE)

def parse_mute_time(token: str) -> Tuple[Optional[datetime], str, bool]:
    """
    Парсит строку времени ('10m', '2h', '1d', 'perm').
    Возвращает: (expires_at, человекочитаемая_строка, успешно_распознано)
    Если 'perm' -> (None, 'навсегда', True)
    """
    token_clean = token.strip().lower()
    if token_clean in ("perm", "forever", "навсегда", "0"):
        return None, "навсегда", True

    match = TIME_PATTERN.match(token_clean)
    if not match:
        return None, "", False

    amount = int(match.group(1))
    unit = match.group(2)

    if amount <= 0:
        return None, "навсегда", True

    now = datetime.now(timezone.utc)
    if unit in ("s", "с"):
        delta = timedelta(seconds=amount)
        label = f"{amount} сек."
    elif unit in ("m", "м"):
        delta = timedelta(minutes=amount)
        label = f"{amount} мин."
    elif unit in ("h", "ч"):
        delta = timedelta(hours=amount)
        label = f"{amount} ч."
    elif unit in ("d", "д"):
        delta = timedelta(days=amount)
        label = f"{amount} дн."
    else:
        return None, "", False

    return now + delta, label, True
