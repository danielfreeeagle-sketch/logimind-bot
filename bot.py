import asyncio
import base64
import json
import logging
import os
import sqlite3
import aiohttp
from datetime import datetime, date, timedelta
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery, PreCheckoutQuery,
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    LabeledPrice
)
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not BOT_TOKEN:
    print("❌ BOT_TOKEN не найден!")
    exit(1)
if not GROQ_API_KEY:
    print("❌ GROQ_API_KEY не найден!")
    exit(1)

OWNER_ID = 7880085486

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

FREE_DAILY_LIMIT = 30
MAX_BONUS_DAYS = 20

# Реферальная система
REFERRAL_BONUS_OWNER = 5    # +5 запросов пригласившему
REFERRAL_BONUS_FRIEND = 3   # +3 запросов приглашённому

PREMIUM_PLANS = {
    "1week":   {"title": "⭐ Premium на 1 неделю",   "price": 25,  "days": 7,     "description": "Попробовать безлимит на 7 дней"},
    "1month":  {"title": "⭐ Premium на 1 месяц",    "price": 75,  "days": 30,    "description": "Безлимит запросов, история 50 сообщений"},
    "3month":  {"title": "⭐ Premium на 3 месяца",   "price": 180, "days": 90,    "description": "Безлимит на 90 дней. Выгода 20%!"},
    "6month":  {"title": "⭐ Premium на 6 месяцев",  "price": 320, "days": 180,   "description": "Безлимит на 180 дней. Выгода 30%!"},
    "1year":   {"title": "⭐ Premium на 1 год",      "price": 550, "days": 365,   "description": "Безлимит на год. Выгода 40%!"},
    "forever": {"title": "⭐ Premium навсегда",      "price": 900, "days": 36500, "description": "Безлимит навсегда + все будущие фичи"},
}

ACHIEVEMENTS = {
    "first_step":     {"icon": "🌱", "name": "Первый шаг",           "desc": "Сделал первый запрос к AI"},
    "first_photo":    {"icon": "📷", "name": "Первое фото",          "desc": "Отправил первое фото"},
    "first_bonus":    {"icon": "🎁", "name": "Первый бонус",         "desc": "Получил ежедневный бонус"},
    "streak_3":       {"icon": "🔥", "name": "На волне",             "desc": "Стрик 3 дня"},
    "streak_7":       {"icon": "🔥🔥", "name": "Неделя силы",         "desc": "Стрик 7 дней"},
    "streak_20":      {"icon": "💎", "name": "Максимум бонуса",      "desc": "Стрик 20 дней"},
    "streak_30":      {"icon": "💎💎", "name": "Месяц дисциплины",     "desc": "Стрик 30 дней"},
    "streak_100":     {"icon": "👑", "name": "Легенда",              "desc": "Стрик 100 дней"},
    "streak_365":     {"icon": "🏆", "name": "Год с нами",           "desc": "Стрик 365 дней"},
    "requests_10":    {"icon": "📚", "name": "Любознательный",       "desc": "10 запросов"},
    "requests_50":    {"icon": "📖", "name": "Ученик",               "desc": "50 запросов"},
    "requests_100":   {"icon": "🎓", "name": "Студент",              "desc": "100 запросов"},
    "requests_500":   {"icon": "🧠", "name": "Мастер",               "desc": "500 запросов"},
    "requests_1000":  {"icon": "🧙", "name": "Гуру",                 "desc": "1000 запросов"},
    "top_100":        {"icon": "🥉", "name": "В ТОП-100",            "desc": "Попал в ТОП-100"},
    "top_10":         {"icon": "🥈", "name": "В ТОП-10",             "desc": "Попал в ТОП-10"},
    "top_3":          {"icon": "🥇", "name": "В ТОП-3",              "desc": "Попал в ТОП-3"},
    "top_1":          {"icon": "🏆", "name": "№1",                   "desc": "Стал первым в топе"},
    "premium":        {"icon": "⭐", "name": "Premium",              "desc": "Купил Premium"},
    "gift_first":     {"icon": "🎁", "name": "Первый подарок",       "desc": "Подарил Premium другу"},
    "gift_3":         {"icon": "💝", "name": "Щедрая душа",          "desc": "Подарил 3 Premium"},
    "gift_10":        {"icon": "👑", "name": "Меценат",              "desc": "Подарил 10 Premium"},
    "gift_25":        {"icon": "💎", "name": "Санта",                "desc": "Подарил 25 Premium"},
    "referral_first": {"icon": "👥", "name": "Первый друг",          "desc": "Пригласил 1 друга"},
    "referral_5":     {"icon": "👨‍👩‍👦", "name": "Компания",           "desc": "Пригласил 5 друзей"},
    "referral_25":    {"icon": "👑", "name": "Король рефералов",     "desc": "Пригласил 25 друзей"},
}

# Стрик-награды (вехи)
STREAK_REWARDS = {
    7:   1,     # 7 дней → Premium на 1 день
    14:  3,     # 14 дней → Premium на 3 дня
    30:  7,     # 30 дней → Premium на 7 дней
    60:  15,    # 60 дней → Premium на 15 дней
    100: 30,    # 100 дней → Premium на 30 дней
    365: 36500, # 365 дней → Premium навсегда
}

# Режимы AI
AI_MODES = {
    "teacher": {
        "icon": "🎓",
        "name": "Учитель",
        "desc": "Объясняет шаг за шагом, как преподаватель",
        "premium": False,
        "prompt": (
            "Ты — logiMind, учитель. Объясняй пошагово, как преподаватель. "
            "Отвечай понятно, дружелюбно. Если это домашка — веди юзера к ответу, "
            "показывай шаги решения. Пиши структурированно."
        )
    },
    "fast": {
        "icon": "🚀",
        "name": "Быстро",
        "desc": "Короткий ответ, без воды",
        "premium": False,
        "prompt": (
            "Ты — logiMind. Отвечай коротко и по делу. Минимум слов, "
            "только суть. Без длинных объяснений."
        )
    },
    "detailed": {
        "icon": "🧠",
        "name": "Подробно",
        "desc": "Полное решение с объяснениями",
        "premium": True,
        "prompt": (
            "Ты — logiMind. Давай максимально подробный ответ. "
            "Объясняй каждую часть, показывай примеры, разбирай варианты. "
            "Отвечай как для студента."
        )
    },
    "simple": {
        "icon": "💡",
        "name": "Просто",
        "desc": "Как 5-летнему, на пальцах",
        "premium": True,
        "prompt": (
            "Ты — logiMind. Объясняй очень просто, как будто юзеру 5 лет. "
            "Используй простые слова, аналогии, примеры из жизни."
        )
    },
}

DB_PATH = "data/users.db"
os.makedirs("data", exist_ok=True)


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            registered_at TEXT,
            last_seen TEXT,
            requests_today INTEGER DEFAULT 0,
            last_reset_date TEXT,
            total_requests INTEGER DEFAULT 0,
            is_premium INTEGER DEFAULT 0,
            premium_until TEXT,
            bonus_streak INTEGER DEFAULT 0,
            last_bonus_date TEXT,
            achievements TEXT DEFAULT '[]',
            ai_mode TEXT DEFAULT 'teacher',
            referral_code TEXT,
            referred_by INTEGER,
            referrals_count INTEGER DEFAULT 0,
            streak_rewards_claimed TEXT DEFAULT '[]'
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gifts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_user_id INTEGER,
            to_user_id INTEGER,
            plan_key TEXT,
            price INTEGER,
            created_at TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS promos (
            code TEXT PRIMARY KEY,
            promo_type TEXT,
            value INTEGER,
            max_uses INTEGER DEFAULT 0,
            used_count INTEGER DEFAULT 0,
            expires_at TEXT,
            created_at TEXT,
            created_by INTEGER
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS promo_uses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT,
            user_id INTEGER,
            used_at TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            title TEXT,
            link TEXT,
            description TEXT,
            total_views INTEGER,
            current_views INTEGER DEFAULT 0,
            package TEXT,
            price INTEGER,
            status TEXT DEFAULT 'active',
            created_at TEXT
        )
    """)

    # Миграция существующих пользователей
    cursor.execute("PRAGMA table_info(users)")
    columns = [c[1] for c in cursor.fetchall()]
    if "bonus_streak" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN bonus_streak INTEGER DEFAULT 0")
    if "last_bonus_date" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN last_bonus_date TEXT")
    if "achievements" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN achievements TEXT DEFAULT '[]'")
    if "ai_mode" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN ai_mode TEXT DEFAULT 'teacher'")
    if "referral_code" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN referral_code TEXT")
    if "referred_by" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN referred_by INTEGER")
    if "referrals_count" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN referrals_count INTEGER DEFAULT 0")
    if "streak_rewards_claimed" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN streak_rewards_claimed TEXT DEFAULT '[]'")

    conn.commit()
    conn.close()
    logger.info("БД инициализирована")


def get_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return {
        "user_id": row[0], "username": row[1], "first_name": row[2],
        "registered_at": row[3], "last_seen": row[4],
        "requests_today": row[5], "last_reset_date": row[6],
        "total_requests": row[7], "is_premium": bool(row[8]), "premium_until": row[9],
        "bonus_streak": row[10] if len(row) > 10 else 0,
        "last_bonus_date": row[11] if len(row) > 11 else None,
        "achievements": json.loads(row[12]) if len(row) > 12 and row[12] else [],
        "ai_mode": row[13] if len(row) > 13 and row[13] else "teacher",
        "referral_code": row[14] if len(row) > 14 else None,
        "referred_by": row[15] if len(row) > 15 else None,
        "referrals_count": row[16] if len(row) > 16 and row[16] else 0,
        "streak_rewards_claimed": json.loads(row[17]) if len(row) > 17 and row[17] else []
    }


def is_premium_active(user):
    if not user or not user["is_premium"] or not user["premium_until"]:
        return False
    try:
        return datetime.fromisoformat(user["premium_until"]) > datetime.now()
    except Exception:
        return False


def get_effective_limit(user):
    base = FREE_DAILY_LIMIT
    bonus = min(user.get("bonus_streak", 0), MAX_BONUS_DAYS) if user else 0
    return base + bonus


def generate_referral_code(user_id):
    return f"ref{user_id}"


def create_or_update_user(user_id, username, first_name):
    today = date.today().isoformat()
    now = datetime.now().isoformat()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, last_reset_date, referral_code FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row is None:
        ref_code = generate_referral_code(user_id)
        cursor.execute("""
            INSERT INTO users (user_id, username, first_name, registered_at, last_seen,
                               requests_today, last_reset_date, total_requests, is_premium,
                               bonus_streak, last_bonus_date, achievements, ai_mode,
                               referral_code, referrals_count, streak_rewards_claimed)
            VALUES (?, ?, ?, ?, ?, 0, ?, 0, 0, 0, NULL, '[]', 'teacher', ?, 0, '[]')
        """, (user_id, username, first_name, now, now, today, ref_code))
    else:
        if row[1] != today:
            cursor.execute("""
                UPDATE users SET last_seen = ?, username = ?, first_name = ?,
                    requests_today = 0, last_reset_date = ? WHERE user_id = ?
            """, (now, username, first_name, today, user_id))
        else:
            cursor.execute("""
                UPDATE users SET last_seen = ?, username = ?, first_name = ?
                WHERE user_id = ?
            """, (now, username, first_name, user_id))
        # Если нет referral_code — добавим
        if not row[2]:
            cursor.execute("UPDATE users SET referral_code = ? WHERE user_id = ?",
                           (generate_referral_code(user_id), user_id))
    conn.commit()
    conn.close()


def check_and_increment_limit(user_id):
    today = date.today().isoformat()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT requests_today, last_reset_date, is_premium, premium_until, bonus_streak FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False, 0, 0
    requests_today, last_reset_date, is_premium, premium_until, bonus_streak = row
    is_active = False
    if is_premium and premium_until:
        try:
            if datetime.fromisoformat(premium_until) > datetime.now():
                is_active = True
            else:
                cursor.execute("UPDATE users SET is_premium = 0, premium_until = NULL WHERE user_id = ?", (user_id,))
        except Exception:
            pass
    if last_reset_date != today:
        requests_today = 0
        cursor.execute("UPDATE users SET requests_today = 0, last_reset_date = ? WHERE user_id = ?", (today, user_id))
    if is_active:
        cursor.execute("UPDATE users SET requests_today = requests_today + 1, total_requests = total_requests + 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
        return True, 999, 999
    effective_limit = FREE_DAILY_LIMIT + min(bonus_streak or 0, MAX_BONUS_DAYS)
    if requests_today >= effective_limit:
        conn.commit()
        conn.close()
        return False, 0, effective_limit
    cursor.execute("UPDATE users SET requests_today = requests_today + 1, total_requests = total_requests + 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    cursor.execute("SELECT requests_today FROM users WHERE user_id = ?", (user_id,))
    new_count = cursor.fetchone()[0]
    conn.close()
    return True, effective_limit - new_count, effective_limit


def add_extra_requests(user_id, count):
    """Добавляет юзеру дополнительные запросы (уменьшает счётчик)."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET requests_today = MAX(0, requests_today - ?) WHERE user_id = ?", (count, user_id))
    conn.commit()
    conn.close()


def activate_premium(user_id, days):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT premium_until, is_premium FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    now = datetime.now()
    if row and row[0] and row[1]:
        try:
            current_until = datetime.fromisoformat(row[0])
            new_until = current_until + timedelta(days=days) if current_until > now else now + timedelta(days=days)
        except Exception:
            new_until = now + timedelta(days=days)
    else:
        new_until = now + timedelta(days=days)
    cursor.execute("UPDATE users SET is_premium = 1, premium_until = ? WHERE user_id = ?", (new_until.isoformat(), user_id))
    conn.commit()
    conn.close()
    return new_until


def deactivate_premium(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET is_premium = 0, premium_until = NULL WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def claim_daily_bonus(user_id):
    today = date.today()
    today_str = today.isoformat()
    yesterday_str = (today - timedelta(days=1)).isoformat()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT last_bonus_date, bonus_streak FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False, "Сначала напиши /start", 0
    last_bonus, streak = row
    streak = streak or 0
    if last_bonus == today_str:
        conn.close()
        return False, "already", streak
    if last_bonus == yesterday_str:
        new_streak = streak + 1
    else:
        new_streak = 1
    cursor.execute("UPDATE users SET last_bonus_date = ?, bonus_streak = ? WHERE user_id = ?", (today_str, new_streak, user_id))
    conn.commit()
    conn.close()
    return True, "ok", new_streak


def check_streak_rewards(user_id):
    """Проверяет и выдаёт награды за стрик. Возвращает список выданных наград."""
    user = get_user(user_id)
    if not user:
        return []
    streak = user.get("bonus_streak", 0) or 0
    claimed = user.get("streak_rewards_claimed", [])
    new_rewards = []

    for milestone, days in sorted(STREAK_REWARDS.items()):
        if streak >= milestone and str(milestone) not in claimed:
            # Выдаём награду
            until = activate_premium(user_id, days)
            claimed.append(str(milestone))
            new_rewards.append({
                "milestone": milestone,
                "days": days,
                "until": until
            })

    if new_rewards:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET streak_rewards_claimed = ? WHERE user_id = ?",
                       (json.dumps(claimed), user_id))
        conn.commit()
        conn.close()

    return new_rewards


def add_achievement(user_id, key):
    if key not in ACHIEVEMENTS:
        return False
    user = get_user(user_id)
    if not user or key in user["achievements"]:
        return False
    ach_list = user["achievements"]
    ach_list.append(key)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET achievements = ? WHERE user_id = ?", (json.dumps(ach_list), user_id))
    conn.commit()
    conn.close()
    return True


def check_achievements(user_id):
    user = get_user(user_id)
    if not user:
        return []
    new = []
    if user["total_requests"] >= 1:
        if add_achievement(user_id, "first_step"):
            new.append("first_step")
    for t, k in [(10, "requests_10"), (50, "requests_50"), (100, "requests_100"), (500, "requests_500"), (1000, "requests_1000")]:
        if user["total_requests"] >= t:
            if add_achievement(user_id, k):
                new.append(k)
    streak = user.get("bonus_streak", 0) or 0
    for t, k in [(3, "streak_3"), (7, "streak_7"), (20, "streak_20"), (30, "streak_30"), (100, "streak_100"), (365, "streak_365")]:
        if streak >= t:
            if add_achievement(user_id, k):
                new.append(k)
    if is_premium_active(user):
        if add_achievement(user_id, "premium"):
            new.append("premium")
    refs = user.get("referrals_count", 0) or 0
    for t, k in [(1, "referral_first"), (5, "referral_5"), (25, "referral_25")]:
        if refs >= t:
            if add_achievement(user_id, k):
                new.append(k)
    return new


def get_stats():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM users WHERE is_premium = 1 AND premium_until > ?", (datetime.now().isoformat(),))
    premium_users = cursor.fetchone()[0]
    cursor.execute("SELECT SUM(total_requests) FROM users")
    total_requests = cursor.fetchone()[0] or 0
    today = date.today().isoformat()
    cursor.execute("SELECT SUM(requests_today) FROM users WHERE last_reset_date = ?", (today,))
    today_requests = cursor.fetchone()[0] or 0
    yesterday = (datetime.now() - timedelta(days=1)).isoformat()
    cursor.execute("SELECT COUNT(*) FROM users WHERE last_seen > ?", (yesterday,))
    active_24h = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM users WHERE bonus_streak >= 7")
    streak_7 = cursor.fetchone()[0]
    conn.close()
    return {"total_users": total_users, "premium_users": premium_users,
            "total_requests": total_requests, "today_requests": today_requests,
            "active_24h": active_24h, "streak_7": streak_7}


def get_top_users(limit=10, today=False):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if today:
        today_str = date.today().isoformat()
        cursor.execute("SELECT user_id, first_name, username, requests_today, is_premium, premium_until FROM users WHERE last_reset_date = ? AND requests_today > 0 ORDER BY requests_today DESC LIMIT ?", (today_str, limit))
    else:
        cursor.execute("SELECT user_id, first_name, username, total_requests, is_premium, premium_until FROM users WHERE total_requests > 0 ORDER BY total_requests DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_top_streaks(limit=10):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, first_name, username, bonus_streak, is_premium, premium_until FROM users WHERE bonus_streak > 0 ORDER BY bonus_streak DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_top_referrals(limit=10):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, first_name, username, referrals_count, is_premium, premium_until FROM users WHERE referrals_count > 0 ORDER BY referrals_count DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_user_rank(user_id, today=False):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if today:
        today_str = date.today().isoformat()
        cursor.execute("SELECT requests_today FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return None
        my_score = row[0]
        cursor.execute("SELECT COUNT(*) FROM users WHERE last_reset_date = ? AND requests_today > ?", (today_str, my_score))
        rank = cursor.fetchone()[0] + 1
        cursor.execute("SELECT COUNT(*) FROM users WHERE last_reset_date = ? AND requests_today > 0", (today_str,))
        total = cursor.fetchone()[0]
    else:
        cursor.execute("SELECT total_requests FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return None
        my_score = row[0]
        cursor.execute("SELECT COUNT(*) FROM users WHERE total_requests > ?", (my_score,))
        rank = cursor.fetchone()[0] + 1
        cursor.execute("SELECT COUNT(*) FROM users WHERE total_requests > 0")
        total = cursor.fetchone()[0]
    conn.close()
    return {"rank": rank, "total": total, "score": my_score}


def get_recent_users(limit=20):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, first_name, username, registered_at, total_requests, is_premium, bonus_streak FROM users ORDER BY registered_at DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_score_needed_for_top(top_n, today=False):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if today:
        today_str = date.today().isoformat()
        cursor.execute("SELECT requests_today FROM users WHERE last_reset_date = ? AND requests_today > 0 ORDER BY requests_today DESC LIMIT 1 OFFSET ?", (today_str, top_n - 1))
    else:
        cursor.execute("SELECT total_requests FROM users WHERE total_requests > 0 ORDER BY total_requests DESC LIMIT 1 OFFSET ?", (top_n - 1,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


def set_streak_admin(user_id, streak):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET bonus_streak = ? WHERE user_id = ?", (streak, user_id))
    conn.commit()
    conn.close()


def set_ai_mode(user_id, mode):
    if mode not in AI_MODES:
        return False
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET ai_mode = ? WHERE user_id = ?", (mode, user_id))
    conn.commit()
    conn.close()
    return True


def create_gift(from_user_id, to_user_id, plan_key, price):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO gifts (from_user_id, to_user_id, plan_key, price, created_at) VALUES (?, ?, ?, ?, ?)",
                   (from_user_id, to_user_id, plan_key, price, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    plan = PREMIUM_PLANS.get(plan_key)
    if not plan:
        return False, None
    until = activate_premium(to_user_id, plan["days"])
    return True, until


def count_gifts_from(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM gifts WHERE from_user_id = ?", (user_id,))
    count = cursor.fetchone()[0]
    conn.close()
    return count


def find_user_by_username(username):
    if not username:
        return None
    username = username.lstrip("@").lower()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE LOWER(username) = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


def check_gift_achievements(user_id):
    count = count_gifts_from(user_id)
    new = []
    for threshold, key in [(1, "gift_first"), (3, "gift_3"), (10, "gift_10"), (25, "gift_25")]:
        if count >= threshold:
            if add_achievement(user_id, key):
                new.append(key)
    return new


# ============ РЕФЕРАЛКА ============
def process_referral(new_user_id, ref_code):
    """Обрабатывает реферальный код. Возвращает (owner_id, owner_bonus, friend_bonus)."""
    if not ref_code:
        return None, 0, 0
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE referral_code = ?", (ref_code,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None, 0, 0
    owner_id = row[0]
    if owner_id == new_user_id:
        conn.close()
        return None, 0, 0  # Нельзя пригласить самого себя
    cursor.execute("SELECT referred_by FROM users WHERE user_id = ?", (new_user_id,))
    existing = cursor.fetchone()
    if existing and existing[0]:
        conn.close()
        return None, 0, 0  # Уже был приглашён
    # Обновляем
    cursor.execute("UPDATE users SET referred_by = ? WHERE user_id = ?", (owner_id, new_user_id))
    cursor.execute("UPDATE users SET referrals_count = referrals_count + 1 WHERE user_id = ?", (owner_id,))
    conn.commit()
    conn.close()
    # Начисляем бонусы (запросы)
    add_extra_requests(owner_id, REFERRAL_BONUS_OWNER)
    add_extra_requests(new_user_id, REFERRAL_BONUS_FRIEND)
    # Проверка ачивок
    check_achievements(owner_id)
    return owner_id, REFERRAL_BONUS_OWNER, REFERRAL_BONUS_FRIEND


# ============ ПРОМОКОДЫ ============
def create_promo(code, promo_type, value, max_uses=0, days_valid=0, created_by=None):
    """Создаёт промокод. promo_type: premium / requests / streak"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    expires_at = None
    if days_valid > 0:
        expires_at = (datetime.now() + timedelta(days=days_valid)).isoformat()
    try:
        cursor.execute("""
            INSERT INTO promos (code, promo_type, value, max_uses, used_count, expires_at, created_at, created_by)
            VALUES (?, ?, ?, ?, 0, ?, ?, ?)
        """, (code.upper(), promo_type, value, max_uses, expires_at, datetime.now().isoformat(), created_by))
        conn.commit()
        ok = True
    except sqlite3.IntegrityError:
        ok = False
    conn.close()
    return ok


def get_promo(code):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM promos WHERE code = ?", (code.upper(),))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return {
        "code": row[0], "promo_type": row[1], "value": row[2],
        "max_uses": row[3], "used_count": row[4],
        "expires_at": row[5], "created_at": row[6], "created_by": row[7]
    }


def use_promo(user_id, code):
    """Активирует промокод. Возвращает (ok, result_dict, error_message)."""
    promo = get_promo(code)
    if not promo:
        return False, None, "not_found"
    # Проверка срока
    if promo["expires_at"]:
        try:
            if datetime.fromisoformat(promo["expires_at"]) < datetime.now():
                return False, None, "expired"
        except Exception:
            pass
    # Проверка лимита
    if promo["max_uses"] > 0 and promo["used_count"] >= promo["max_uses"]:
        return False, None, "limit_reached"
    # Проверка: юзер уже использовал?
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM promo_uses WHERE code = ? AND user_id = ?", (promo["code"], user_id))
    if cursor.fetchone():
        conn.close()
        return False, None, "already_used"
    # Активируем
    cursor.execute("INSERT INTO promo_uses (code, user_id, used_at) VALUES (?, ?, ?)",
                   (promo["code"], user_id, datetime.now().isoformat()))
    cursor.execute("UPDATE promos SET used_count = used_count + 1 WHERE code = ?", (promo["code"],))
    conn.commit()
    conn.close()
    # Выдаём награду
    result = {"type": promo["promo_type"], "value": promo["value"]}
    if promo["promo_type"] == "premium":
        until = activate_premium(user_id, promo["value"])
        result["until"] = until
        add_achievement(user_id, "premium")
    elif promo["promo_type"] == "requests":
        add_extra_requests(user_id, promo["value"])
    elif promo["promo_type"] == "streak":
        user = get_user(user_id)
        if user:
            new_streak = (user.get("bonus_streak", 0) or 0) + promo["value"]
            set_streak_admin(user_id, new_streak)
            result["new_streak"] = new_streak
            check_achievements(user_id)
    return True, result, None


def delete_promo(code):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM promos WHERE code = ?", (code.upper(),))
    conn.commit()
    conn.close()


def list_promos():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM promos ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_user_promo_history(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT code, used_at FROM promo_uses WHERE user_id = ? ORDER BY used_at DESC LIMIT 20", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows


# ============ РЕКЛАМА (базовая — только твоя) ============
def add_ad(user_id, title, link, description, total_views, package="custom", price=0):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO ads (user_id, title, link, description, total_views, package, price, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?)
    """, (user_id, title, link, description, total_views, package, price, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def get_active_ads():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM ads WHERE status = 'active' AND current_views < total_views ORDER BY id")
    rows = cursor.fetchall()
    conn.close()
    return rows


def increment_ad_view(ad_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE ads SET current_views = current_views + 1 WHERE id = ?", (ad_id,))
    cursor.execute("SELECT current_views, total_views FROM ads WHERE id = ?", (ad_id,))
    row = cursor.fetchone()
    if row and row[0] >= row[1]:
        cursor.execute("UPDATE ads SET status = 'finished' WHERE id = ?", (ad_id,))
    conn.commit()
    conn.close()


def list_ads():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM ads ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return rows


def delete_ad(ad_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM ads WHERE id = ?", (ad_id,))
    conn.commit()
    conn.close()


pending_states = {}


# ============ БОТ ============
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# ============ AI ============
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL_TEXT = "openai/gpt-oss-120b"
GROQ_MODEL_VISION = "qwen/qwen3.8-27b"

SYSTEM_PROMPT_VISION = (
    "Ты — logiMind, помощник по учёбе. Пользователь прислал фото задания. "
    "Прочитай текст, пойми задачу и помоги решить. Отвечай на языке задания."
)

user_histories = {}
MAX_HISTORY_FREE = 10
MAX_HISTORY_PREMIUM = 50


def get_history(user_id):
    if user_id not in user_histories:
        user_histories[user_id] = []
    return user_histories[user_id]


def add_to_history(user_id, role, content, is_premium=False):
    history = get_history(user_id)
    history.append({"role": role, "content": content})
    max_hist = MAX_HISTORY_PREMIUM if is_premium else MAX_HISTORY_FREE
    if len(history) > max_hist * 2:
        user_histories[user_id] = history[-max_hist * 2:]


def get_mode_prompt(mode_key):
    """Возвращает SYSTEM_PROMPT для режима."""
    mode = AI_MODES.get(mode_key)
    if not mode:
        mode = AI_MODES["teacher"]
    return mode["prompt"]


async def ask_ai(user_id: int, user_message: str, is_premium: bool = False, mode_key: str = "teacher") -> str:
    add_to_history(user_id, "user", user_message, is_premium)
    system_prompt = get_mode_prompt(mode_key)
    messages = [{"role": "system", "content": system_prompt}] + get_history(user_id)
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": GROQ_MODEL_TEXT, "messages": messages, "temperature": 0.7, "max_tokens": 1500}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(GROQ_URL, headers=headers, json=payload, timeout=60) as resp:
                if resp.status != 200:
                    err = await resp.text()
                    logger.error(f"Groq error {resp.status}: {err[:200]}")
                    return f"⚠️ Ошибка AI (код {resp.status})."
                data = await resp.json()
                answer = data["choices"][0]["message"]["content"]
                add_to_history(user_id, "assistant", answer, is_premium)
                return answer
    except asyncio.TimeoutError:
        return "⚠️ AI не ответил вовремя."
    except Exception as e:
        logger.error(f"AI error: {e}")
        return "⚠️ Что-то сломалось."


async def ask_ai_vision(user_id: int, image_base64: str, caption: str = "") -> str:
    user_text = caption if caption else "Прочитай задание на фото и помоги решить."
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT_VISION},
        {"role": "user", "content": [
            {"type": "text", "text": user_text},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}}
        ]}
    ]
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": GROQ_MODEL_VISION, "messages": messages, "temperature": 0.5, "max_tokens": 1500}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(GROQ_URL, headers=headers, json=payload, timeout=90) as resp:
                if resp.status != 200:
                    err = await resp.text()
                    logger.error(f"Groq vision {resp.status}: {err[:300]}")
                    if resp.status == 400:
                        return "⚠️ Не могу разобрать фото."
                    if resp.status == 429:
                        return "⚠️ Слишком много фото. Подожди."
                    return f"⚠️ Ошибка AI (код {resp.status})."
                data = await resp.json()
                return data["choices"][0]["message"]["content"]
    except asyncio.TimeoutError:
        return "⚠️ AI не успел обработать фото."
    except Exception as e:
        logger.error(f"Vision error: {e}")
        return "⚠️ Что-то сломалось."


# ============ УТИЛИТЫ ============
def is_admin(user_id):
    return user_id == OWNER_ID


def get_premium_icon(is_premium_field, premium_until_field):
    if not is_premium_field or not premium_until_field:
        return ""
    try:
        if datetime.fromisoformat(premium_until_field) > datetime.now():
            return " ⭐"
    except Exception:
        pass
    return ""


def streak_fire(streak):
    if not streak:
        return ""
    if streak >= 100:
        return " 👑"
    if streak >= 30:
        return " 💎💎"
    if streak >= 20:
        return " 💎"
    if streak >= 14:
        return " ⚡"
    if streak >= 7:
        return " 🔥🔥"
    if streak >= 3:
        return " 🔥"
    return ""


def get_achievement_label(rank, total):
    if total == 0 or rank is None:
        return ""
    if rank == 1:
        return "🏆 <b>Ты на 1 месте! Легенда!</b>"
    if rank <= 3:
        return f"🥇 <b>Ты в ТОП-3</b> (место {rank})"
    if rank <= 10:
        return f"🥈 <b>Ты в ТОП-10</b> (место {rank})"
    if rank <= 100:
        return f"🥉 <b>Ты в ТОП-100</b> (место {rank})"
    return f"📍 Ты на <b>{rank}</b> месте из {total}"


def make_progress_bar(value, maximum, length=10):
    if maximum <= 0:
        return "░" * length
    filled = min(int(length * value / maximum), length)
    return "█" * filled + "░" * (length - filled)


def get_next_streak_reward(streak, claimed):
    """Возвращает следующую награду: (milestone, days) или None."""
    for milestone, days in sorted(STREAK_REWARDS.items()):
        if streak < milestone and str(milestone) not in claimed:
            return milestone, days
    return None


# ============ МЕНЮ ============
def get_main_menu(user_id=None):
    if user_id == OWNER_ID:
        return ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="🤖 Спросить AI"), KeyboardButton(text="🎁 Бонус")],
                [KeyboardButton(text="📚 Помощь с ДЗ"), KeyboardButton(text="👤 Профиль")],
                [KeyboardButton(text="🥇 Топ"), KeyboardButton(text="🔥 Стрики"), KeyboardButton(text="⭐ Premium")],
                [KeyboardButton(text="⚙️ Режим AI"), KeyboardButton(text="👥 Пригласить")],
                [KeyboardButton(text="👑 БОСС-ПАНЕЛЬ"), KeyboardButton(text="❓ Помощь")]
            ],
            resize_keyboard=True,
            input_field_placeholder="👑 Режим БОССА активен..."
        )
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🤖 Спросить AI"), KeyboardButton(text="🎁 Бонус")],
            [KeyboardButton(text="📚 Помощь с ДЗ"), KeyboardButton(text="👤 Профиль")],
            [KeyboardButton(text="🥇 Топ"), KeyboardButton(text="🔥 Стрики"), KeyboardButton(text="⭐ Premium")],
            [KeyboardButton(text="⚙️ Режим AI"), KeyboardButton(text="👥 Пригласить")],
            [KeyboardButton(text="❓ Помощь")]
        ],
        resize_keyboard=True,
        input_field_placeholder="Напиши вопрос или пришли фото..."
    )


def get_premium_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ 1 неделя — 25 звёзд", callback_data="buy_1week")],
        [InlineKeyboardButton(text="⭐ 1 месяц — 75 звёзд", callback_data="buy_1month")],
        [InlineKeyboardButton(text="⭐ 3 месяца — 180 звёзд 🔥", callback_data="buy_3month")],
        [InlineKeyboardButton(text="⭐ 6 месяцев — 320 звёзд", callback_data="buy_6month")],
        [InlineKeyboardButton(text="⭐ 1 год — 550 звёзд 💎", callback_data="buy_1year")],
        [InlineKeyboardButton(text="⭐ Навсегда — 900 звёзд 👑", callback_data="buy_forever")],
        [InlineKeyboardButton(text="🎁 Подарить другу", callback_data="gift_start")],
    ])


def get_gift_plans_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 1 неделя — 25 звёзд", callback_data="giftbuy_1week")],
        [InlineKeyboardButton(text="🎁 1 месяц — 75 звёзд", callback_data="giftbuy_1month")],
        [InlineKeyboardButton(text="🎁 3 месяца — 180 звёзд 🔥", callback_data="giftbuy_3month")],
        [InlineKeyboardButton(text="🎁 6 месяцев — 320 звёзд", callback_data="giftbuy_6month")],
        [InlineKeyboardButton(text="🎁 1 год — 550 звёзд 💎", callback_data="giftbuy_1year")],
        [InlineKeyboardButton(text="🎁 Навсегда — 900 звёзд 👑", callback_data="giftbuy_forever")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="gift_cancel")],
    ])


def get_ai_modes_keyboard(current_mode="teacher"):
    buttons = []
    for key, mode in AI_MODES.items():
        icon = mode["icon"]
        name = mode["name"]
        lock = "" if not mode["premium"] else " ⭐"
        check = " ✅" if key == current_mode else ""
        buttons.append([InlineKeyboardButton(
            text=f"{icon} {name}{lock}{check}",
            callback_data=f"setmode_{key}"
        )])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ============ АЧИВКИ (показ) ============
def build_achievements_text(user_id):
    user = get_user(user_id)
    if not user:
        return "Сначала /start"
    got = user["achievements"]
    total = len(ACHIEVEMENTS)
    got_count = len(got)
    text = f"🏆 <b>ТВОИ АЧИВКИ</b>\nПолучено: <b>{got_count}/{total}</b>\n\n"
    text += "━━━━━━━━━━━━━━━━━━━━\n✅ <b>ПОЛУЧЕНО</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
    got_any = False
    for key, ach in ACHIEVEMENTS.items():
        if key in got:
            text += f"{ach['icon']} <b>{ach['name']}</b>\n<i>{ach['desc']}</i>\n\n"
            got_any = True
    if not got_any:
        text += "<i>Пока ничего. Сделай первый запрос!</i>\n\n"
    locked = [k for k in ACHIEVEMENTS if k not in got]
    if locked:
        text += "━━━━━━━━━━━━━━━━━━━━\n🔒 <b>ЗАБЛОКИРОВАНО</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
        for key in locked[:10]:
            ach = ACHIEVEMENTS[key]
            text += f"🔒 <b>{ach['name']}</b>\n<i>{ach['desc']}</i>\n\n"
        if len(locked) > 10:
            text += f"<i>...и ещё {len(locked) - 10} ачивок</i>"
    return text


async def notify_new_achievements(message: Message, new_achievements):
    if not new_achievements:
        return
    for key in new_achievements:
        ach = ACHIEVEMENTS.get(key)
        if not ach:
            continue
        await message.answer(
            f"🎉 <b>НОВАЯ АЧИВКА!</b>\n\n"
            f"{ach['icon']} <b>{ach['name']}</b>\n"
            f"<i>{ach['desc']}</i>\n\n"
            f"Посмотреть все: /achivements"
        )


async def notify_streak_rewards(message: Message, rewards):
    """Уведомляет о наградах за стрик."""
    if not rewards:
        return
    for r in rewards:
        milestone = r["milestone"]
        days = r["days"]
        until = r["until"]
        if days >= 36500:
            until_text = "навсегда"
        else:
            until_text = f"до {until.strftime('%d.%m.%Y')}"
        await message.answer(
            f"🏆 <b>НАГРАДА ЗА СТРИК!</b>\n\n"
            f"🔥 {milestone} дней подряд!\n\n"
            f"⭐ <b>Premium активирован</b> {until_text}\n\n"
            f"Спасибо что с нами! Продолжай в том же духе 🚀"
        )


# ============ ТОП ============
def build_top_text(today=False):
    rows = get_top_users(limit=10, today=today)
    medals = ["🥇", "🥈", "🥉"]
    if today:
        header = "🏆 <b>ТОП-10 СЕГОДНЯ</b>\n🔥 Самые активные сегодня\n\n"
    else:
        header = "🏆 <b>ТОП-10 ЮЗЕРОВ</b>\n📊 За всё время\n\n"
    if not rows:
        return header + "<i>Пока никого нет. Будь первым! 🚀</i>"
    text = header
    for i, (uid, first_name, username, score, is_prem, until) in enumerate(rows, 1):
        medal = medals[i-1] if i <= 3 else f"{i}."
        name = first_name or "Аноним"
        prem_icon = get_premium_icon(is_prem, until)
        u = get_user(uid)
        fire = streak_fire(u.get("bonus_streak", 0) if u else 0)
        fire_icon = " 🔥" if today else ""
        text += f"{medal} <b>{name}</b>{prem_icon}{fire}{fire_icon} — {score} зап.\n"
    text += "\n<i>Хочешь попасть в топ? Спрашивай больше! 🚀</i>"
    return text


def build_streaks_text():
    rows = get_top_streaks(limit=10)
    medals = ["🥇", "🥈", "🥉"]
    header = "🔥 <b>ТОП-10 ПО СТРИКАМ</b>\n💎 Кто дольше всех заходит подряд\n\n"
    if not rows:
        return header + "<i>Пока ни у кого нет стрика. Заходи каждый день — и будешь первым! 🚀</i>"
    text = header
    for i, (uid, first_name, username, streak, is_prem, until) in enumerate(rows, 1):
        medal = medals[i-1] if i <= 3 else f"{i}."
        name = first_name or "Аноним"
        prem_icon = get_premium_icon(is_prem, until)
        fire = streak_fire(streak)
        text += f"{medal} <b>{name}</b>{prem_icon} — {streak} дней{fire}\n"
    text += "\n<i>Заходи каждый день — и поднимайся в топ! 🔥</i>"
    return text


def build_referrals_text():
    rows = get_top_referrals(limit=10)
    medals = ["🥇", "🥈", "🥉"]
    header = "👥 <b>ТОП-10 ПО РЕФЕРАЛАМ</b>\n💎 Кто больше всех привёл друзей\n\n"
    if not rows:
        return header + "<i>Пока никого нет. Пригласи друга — и будь первым! 🚀</i>"
    text = header
    for i, (uid, first_name, username, refs, is_prem, until) in enumerate(rows, 1):
        medal = medals[i-1] if i <= 3 else f"{i}."
        name = first_name or "Аноним"
        prem_icon = get_premium_icon(is_prem, until)
        text += f"{medal} <b>{name}</b>{prem_icon} — {refs} друзей\n"
    text += "\n<i>Приглашай друзей — и поднимайся в топ! 👥</i>"
    return text


def get_streaks_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Топ запросов", callback_data="top_all_time")],
        [InlineKeyboardButton(text="👤 Моё место в стриках", callback_data="my_streak")],
        [InlineKeyboardButton(text="👥 Топ по рефералам", callback_data="top_refs")],
    ])


def get_top_keyboard(today=False):
    if today:
        toggle_text, toggle_cb, my_cb = "📊 За всё время", "top_all_time", "my_rank_today"
    else:
        toggle_text, toggle_cb, my_cb = "🔥 Топ за сегодня", "top_today", "my_rank_all"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📍 Моё место", callback_data=my_cb),
         InlineKeyboardButton(text=toggle_text, callback_data=toggle_cb)],
        [InlineKeyboardButton(text="🔥 Топ по стрикам", callback_data="top_streaks")],
        [InlineKeyboardButton(text="👥 Топ по рефералам", callback_data="top_refs")],
    ])


# ============ КОМАНДЫ ТОПА ============
@dp.message(Command("top"))
async def cmd_top(message: Message):
    create_or_update_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    text = build_top_text(today=False)
    await message.answer(text, reply_markup=get_top_keyboard(today=False))


@dp.message(Command("top_today"))
async def cmd_top_today(message: Message):
    create_or_update_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    text = build_top_text(today=True)
    await message.answer(text, reply_markup=get_top_keyboard(today=True))


@dp.message(Command("top_streaks"))
async def cmd_top_streaks(message: Message):
    create_or_update_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    text = build_streaks_text()
    await message.answer(text, reply_markup=get_streaks_keyboard())


@dp.message(Command("top_refs"))
async def cmd_top_refs(message: Message):
    create_or_update_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    text = build_referrals_text()
    await message.answer(text, reply_markup=get_streaks_keyboard())


@dp.callback_query(F.data == "top_today")
async def cb_top_today(callback: CallbackQuery):
    text = build_top_text(today=True)
    try:
        await callback.message.edit_text(text, reply_markup=get_top_keyboard(today=True))
    except Exception:
        await callback.message.answer(text, reply_markup=get_top_keyboard(today=True))
    await callback.answer()


@dp.callback_query(F.data == "top_all_time")
async def cb_top_all(callback: CallbackQuery):
    text = build_top_text(today=False)
    try:
        await callback.message.edit_text(text, reply_markup=get_top_keyboard(today=False))
    except Exception:
        await callback.message.answer(text, reply_markup=get_top_keyboard(today=False))
    await callback.answer()


@dp.callback_query(F.data == "top_streaks")
async def cb_top_streaks(callback: CallbackQuery):
    text = build_streaks_text()
    try:
        await callback.message.edit_text(text, reply_markup=get_streaks_keyboard())
    except Exception:
        await callback.message.answer(text, reply_markup=get_streaks_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "top_refs")
async def cb_top_refs(callback: CallbackQuery):
    text = build_referrals_text()
    try:
        await callback.message.edit_text(text, reply_markup=get_streaks_keyboard())
    except Exception:
        await callback.message.answer(text, reply_markup=get_streaks_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "my_streak")
async def cb_my_streak(callback: CallbackQuery):
    u = get_user(callback.from_user.id)
    if not u:
        await callback.answer("Сначала напиши /start", show_alert=True)
        return
    streak = u.get("bonus_streak", 0) or 0
    fire = streak_fire(streak)
    claimed = u.get("streak_rewards_claimed", [])
    next_reward = get_next_streak_reward(streak, claimed)

    if streak == 0:
        msg = "🔥 <b>У тебя ещё нет стрика</b>\n\nНачни заходить каждый день и получишь бонус!"
    else:
        msg = (
            f"🔥 <b>Твой стрик:</b> {streak} дней{fire}\n\n"
            f"📊 Бонус к лимиту: <b>+{min(streak, MAX_BONUS_DAYS)}</b>\n"
            f"🎯 Твой лимит сегодня: <b>{get_effective_limit(u)}</b> запросов\n"
        )
        if next_reward:
            milestone, days = next_reward
            remaining = milestone - streak
            msg += (
                f"\n🏆 <b>Следующая награда:</b>\n"
                f"📅 Через {remaining} дней стрик {milestone}\n"
                f"⭐ Premium на {days if days < 36500 else 'навсегда'} дн."
            )
    await callback.answer()
    await callback.message.answer(msg)


@dp.callback_query(F.data == "my_rank_all")
async def cb_my_rank_all(callback: CallbackQuery):
    data = get_user_rank(callback.from_user.id, today=False)
    if not data or data['total'] == 0 or data['score'] == 0:
        await callback.answer("Ты пока не в рейтинге. Спрашивай у AI!", show_alert=True)
        return
    text = (
        f"📍 <b>ТВОЁ МЕСТО (за всё время)</b>\n\n"
        f"Место: <b>{data['rank']}</b> из {data['total']}\n"
        f"Запросов всего: <b>{data['score']}</b>\n\n"
    )
    if data['rank'] > 10:
        s = get_score_needed_for_top(10, today=False)
        if s:
            need = s - data['score'] + 1
            if need > 0:
                text += f"До ТОП-10 осталось: <b>{need}</b> зап.\n"
    text += "\n<i>Спрашивай больше — и попадёшь в топ! 🚀</i>"
    await callback.answer()
    await callback.message.answer(text)


@dp.callback_query(F.data == "my_rank_today")
async def cb_my_rank_today(callback: CallbackQuery):
    data = get_user_rank(callback.from_user.id, today=True)
    if not data or data['total'] == 0 or data['score'] == 0:
        await callback.answer("Сегодня ты ещё не спрашивал. Напиши вопрос!", show_alert=True)
        return
    text = (
        f"📍 <b>ТВОЁ МЕСТО (сегодня)</b>\n\n"
        f"Место: <b>{data['rank']}</b> из {data['total']}\n"
        f"Запросов сегодня: <b>{data['score']}</b>\n\n"
        f"<i>Спрашивай больше — и попадёшь в топ дня! 🔥</i>"
    )
    await callback.answer()
    await callback.message.answer(text)


# ============ /start ============
@dp.message(Command("start"))
async def cmd_start(message: Message):
    user = message.from_user
    create_or_update_user(user.id, user.username, user.first_name)

    # Обработка реферальной ссылки
    args = message.text.split()
    if len(args) > 1:
        ref_code = args[1]
        # Обрабатываем только если юзер новый (referred_by = NULL)
        u = get_user(user.id)
        if u and not u.get("referred_by"):
            owner_id, owner_bonus, friend_bonus = process_referral(user.id, ref_code)
            if owner_id:
                await message.answer(
                    f"🎁 <b>Ты пришёл по ссылке друга!</b>\n\n"
                    f"✅ Тебе +{friend_bonus} запросов\n"
                    f"✅ Твоему другу +{owner_bonus} запросов\n\n"
                    f"<i>Хочешь тоже приглашать? Кнопка «👥 Пригласить» в меню!</i>"
                )
                try:
                    await bot.send_message(
                        owner_id,
                        f"🎉 <b>По твоей ссылке пришёл друг!</b>\n\n"
                        f"✅ Тебе +{owner_bonus} запросов\n\n"
                        f"<i>Продолжай приглашать — за 5 друзей дам ачивку!</i>"
                    )
                except Exception:
                    pass

    user_name = user.first_name or "друг"
    if user.id == OWNER_ID:
        text = (
            f"👑 <b>С возвращением, БОСС {user_name}!</b>\n\n"
            f"🧠 <b>logiMind</b> к твоим услугам.\n\n"
            f"Все системы работают. Бот — твой раб.\n\n"
            f"<b>БОСС-ПАНЕЛЬ доступна в меню 👇</b>\n"
            f"Или команда: <code>/boss</code>"
        )
    else:
        text = (
            f"👋 Привет, <b>{user_name}</b>!\n\n"
            f"🧠 Я <b>logiMind</b> — твой умный помощник по учёбе.\n\n"
            f"Что я умею:\n"
            f"📚 Помогаю разбирать домашние задания\n"
            f"📷 Читаю задания с фотографий\n"
            f"📝 Объясняю сложные темы простыми словами\n"
            f"💬 Отвечаю на любые вопросы\n\n"
            f"🎁 Бесплатно: <b>{FREE_DAILY_LIMIT} запросов в день</b>\n"
            f"🎁 Ежедневный бонус: <b>+1 к лимиту за день подряд</b>\n"
            f"🏆 Premium за стрик (7, 14, 30, 60, 100, 365 дней)\n"
            f"👥 Приглашай друзей — получай бонусы\n"
            f"⭐ Premium: <b>безлимит</b>\n\n"
            f"<b>Напиши вопрос или пришли фото задания 👇</b>"
        )
    await message.answer(text, reply_markup=get_main_menu(user.id))


# ============ /help ============
@dp.message(Command("help"))
async def cmd_help(message: Message):
    text = (
        "❓ <b>Помощь по logiMind</b>\n\n"
        "<b>Что я умею:</b>\n"
        "• Отвечать на любые вопросы\n"
        "• Помогать с домашними заданиями\n"
        "• <b>Читать задания с фотографий 📷</b>\n"
        "• Объяснять темы простыми словами\n\n"
        "<b>Команды:</b>\n"
        "/start — запустить бота\n"
        "/help — эта помощь\n"
        "/profile — мой профиль\n"
        "/achivements — мои ачивки 🏆\n"
        "/bonus — получить бонус 🎁\n"
        "/premium — купить Premium ⭐\n"
        "/mode — режимы AI ⚙️\n"
        "/invite — пригласить друга 👥\n"
        "/promo — ввести промокод 🎫\n"
        "/top — топ юзеров 🏆\n"
        "/top_today — топ за сегодня 🔥\n"
        "/top_streaks — топ по стрикам 🔥🔥\n"
        "/top_refs — топ по рефералам 👥\n"
        "/reset — сбросить диалог\n"
        "/cancel — отменить действие\n\n"
        f"<b>Лимит:</b> {FREE_DAILY_LIMIT} базовых + бонус за стрик (до +{MAX_BONUS_DAYS})"
    )
    await message.answer(text)


# ============ /premium ============
@dp.message(Command("premium"))
async def cmd_premium(message: Message):
    user = get_user(message.from_user.id)

    if user and is_premium_active(user):
        until = datetime.fromisoformat(user["premium_until"])
        if until.year >= 2100:
            status_text = "⭐ <b>У тебя Premium навсегда!</b>\n\nСпасибо за поддержку 🚀"
        else:
            status_text = (
                f"⭐ <b>У тебя Premium активен</b>\n\n"
                f"Действует до: <b>{until.strftime('%d.%m.%Y')}</b>\n\n"
                f"Что можно сделать:"
            )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎁 Подарить Premium другу", callback_data="gift_start")],
            [InlineKeyboardButton(text="⭐ Продлить свой Premium", callback_data="show_buy_menu")],
        ])
        await message.answer(status_text, reply_markup=kb)
        return

    text = (
        "⭐ <b>logiMind Premium</b>\n\n"
        "<b>Что даёт Premium:</b>\n"
        "✅ <b>Безлимит</b> запросов\n"
        "✅ История диалога <b>50 сообщений</b>\n"
        "✅ Значок ⭐ в профиле и топе\n"
        "✅ <b>2 эксклюзивных режима AI</b> (🧠 Подробно, 💡 Просто)\n"
        "✅ Все будущие фичи бесплатно\n\n"
        "<b>Выбери тариф 👇</b>\n"
        "<i>Или подари Premium другу 🎁</i>"
    )
    await message.answer(text, reply_markup=get_premium_keyboard())


@dp.callback_query(F.data == "show_buy_menu")
async def show_buy_menu_cb(callback: CallbackQuery):
    text = (
        "⭐ <b>Продление Premium</b>\n\n"
        "Выбери тариф — он <b>прибавится</b> к твоему текущему Premium.\n\n"
        "<b>Выбери 👇</b>"
    )
    await callback.answer()
    await callback.message.answer(text, reply_markup=get_premium_keyboard())


# ============ РЕЖИМЫ AI ============
@dp.message(Command("mode"))
async def cmd_mode(message: Message):
    user = get_user(message.from_user.id)
    if not user:
        await message.answer("Нажми /start сначала.")
        return
    current = user.get("ai_mode", "teacher")
    text = (
        "⚙️ <b>РЕЖИМЫ AI</b>\n\n"
        "Выбери как AI будет отвечать на твои вопросы:\n\n"
    )
    for key, mode in AI_MODES.items():
        lock = "⭐ " if mode["premium"] else ""
        check = " ✅" if key == current else ""
        text += f"{mode['icon']} <b>{mode['name']}</b>{check}\n"
        text += f"<i>{lock}{mode['desc']}</i>\n\n"
    text += "⭐ — только для Premium\n\n<b>Выбери режим 👇</b>"
    await message.answer(text, reply_markup=get_ai_modes_keyboard(current))


@dp.callback_query(F.data.startswith("setmode_"))
async def cb_set_mode(callback: CallbackQuery):
    mode_key = callback.data.replace("setmode_", "")
    if mode_key not in AI_MODES:
        await callback.answer("Ошибка режима", show_alert=True)
        return
    user = get_user(callback.from_user.id)
    if not user:
        await callback.answer("Нажми /start", show_alert=True)
        return
    mode = AI_MODES[mode_key]
    # Проверка Premium для премиум-режимов
    if mode["premium"] and not is_premium_active(user):
        await callback.answer("⭐ Этот режим только для Premium!", show_alert=True)
        return
    set_ai_mode(callback.from_user.id, mode_key)
    await callback.answer(f"Режим: {mode['name']} ✅", show_alert=False)
    text = (
        f"✅ <b>Режим изменён</b>\n\n"
        f"{mode['icon']} <b>{mode['name']}</b>\n"
        f"<i>{mode['desc']}</i>\n\n"
        f"Теперь AI отвечает в этом стиле."
    )
    try:
        await callback.message.edit_text(text, reply_markup=get_ai_modes_keyboard(mode_key))
    except Exception:
        await callback.message.answer(text, reply_markup=get_ai_modes_keyboard(mode_key))


# ============ РЕФЕРАЛКА ============
@dp.message(Command("invite"))
async def cmd_invite(message: Message):
    user = get_user(message.from_user.id)
    if not user:
        await message.answer("Нажми /start сначала.")
        return
    ref_code = user.get("referral_code") or generate_referral_code(message.from_user.id)
    bot_username = (await bot.get_me()).username
    link = f"https://t.me/{bot_username}?start={ref_code}"
    refs = user.get("referrals_count", 0) or 0

    text = (
        f"👥 <b>ПРИГЛАСИ ДРУЗЕЙ</b>\n\n"
        f"🎁 <b>Что получаешь:</b>\n"
        f"✅ +{REFERRAL_BONUS_OWNER} запросов за каждого друга\n"
        f"✅ Ачивки за 1, 5, 25 друзей\n"
        f"✅ Друг получает +{REFERRAL_BONUS_FRIEND} запросов\n\n"
        f"📊 <b>Твоя статистика:</b>\n"
        f"👥 Приглашено: <b>{refs}</b>\n\n"
        f"🔗 <b>Твоя ссылка:</b>\n"
        f"<code>{link}</code>\n\n"
        f"<i>Нажми на ссылку чтобы скопировать</i>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Поделиться", url=f"https://t.me/share/url?url={link}&text=Попробуй этого AI-помощника для учёбы!")]
    ])
    await message.answer(text, reply_markup=kb)


# ============ ПРОМОКОДЫ ============
@dp.message(Command("promo"))
async def cmd_promo(message: Message):
    args = message.text.split()
    if len(args) < 2:
        await message.answer(
            "🎫 <b>Промокод</b>\n\n"
            "Использование: <code>/promo КОД</code>\n\n"
            "Пример: <code>/promo NEWYEAR</code>"
        )
        return
    code = args[1]
    ok, result, error = use_promo(message.from_user.id, code)

    if not ok:
        errors = {
            "not_found": "❌ Промокод не найден",
            "expired": "⏰ Промокод истёк",
            "limit_reached": "📊 Лимит активаций исчерпан",
            "already_used": "⚠️ Ты уже использовал этот промокод"
        }
        await message.answer(errors.get(error, "❌ Ошибка активации"))
        return

    # Успех
    if result["type"] == "premium":
        until = result["until"]
        if result["value"] >= 36500:
            until_text = "навсегда"
        else:
            until_text = f"до {until.strftime('%d.%m.%Y')}"
        await message.answer(
            f"🎫 <b>ПРОМОКОД АКТИВИРОВАН!</b>\n\n"
            f"⭐ Premium {until_text}"
        )
    elif result["type"] == "requests":
        await message.answer(
            f"🎫 <b>ПРОМОКОД АКТИВИРОВАН!</b>\n\n"
            f"💎 +{result['value']} запросов"
        )
    elif result["type"] == "streak":
        await message.answer(
            f"🎫 <b>ПРОМОКОД АКТИВИРОВАН!</b>\n\n"
            f"🔥 +{result['value']} к стрику\n"
            f"📊 Новый стрик: {result.get('new_streak', 0)}"
        )


@dp.message(Command("my_promos"))
async def cmd_my_promos(message: Message):
    rows = get_user_promo_history(message.from_user.id)
    if not rows:
        await message.answer("🎫 Ты ещё не активировал промокоды.")
        return
    text = "🎫 <b>МОИ ПРОМОКОДЫ</b>\n\n"
    for code, used_at in rows:
        date = used_at[:10]
        text += f"✅ <code>{code}</code> — {date}\n"
    await message.answer(text)


# ============ /profile ============
@dp.message(Command("profile"))
async def cmd_profile(message: Message):
    user_id = message.from_user.id
    user = get_user(user_id)
    if not user:
        await message.answer("Нажми /start сначала.")
        return

    premium_active = is_premium_active(user)
    premium_badge = " ⭐" if premium_active else ""
    rank_data = get_user_rank(user_id, today=False)
    ach_label = ""
    if rank_data and rank_data['total'] > 0 and user['total_requests'] > 0:
        ach_label = get_achievement_label(rank_data['rank'], rank_data['total'])

    mode_key = user.get("ai_mode", "teacher")
    mode = AI_MODES.get(mode_key, AI_MODES["teacher"])

    if premium_active:
        until = datetime.fromisoformat(user["premium_until"])
        limit_block = "⭐ <b>Premium навсегда</b> 🎉" if until.year >= 2100 else f"⭐ <b>Premium</b> до {until.strftime('%d.%m.%Y')} 🎉"
    else:
        effective_limit = get_effective_limit(user)
        remaining = effective_limit - user["requests_today"]
        bar = make_progress_bar(user["requests_today"], effective_limit)
        streak = user.get("bonus_streak", 0) or 0
        fire = streak_fire(streak)
        limit_block = (
            f"📊 Лимит: <b>{effective_limit}</b> запросов\n"
            f"<code>{bar}</code> {user['requests_today']}/{effective_limit}\n"
        )
        if streak > 0:
            limit_block += f"🔥 Стрик: <b>{streak}</b> дней{fire}\n"
        if remaining <= 0:
            limit_block += "❌ <b>Лимит исчерпан</b>"
        elif remaining <= 5:
            limit_block += f"⚠️ <b>Осталось: {remaining}</b>"
        else:
            limit_block += f"✅ <b>Осталось: {remaining}</b>"

    ach_count = len(user["achievements"])
    ach_total = len(ACHIEVEMENTS)
    gifts_count = count_gifts_from(user_id)
    refs = user.get("referrals_count", 0) or 0

    # Инфо о следующей награде за стрик
    streak = user.get("bonus_streak", 0) or 0
    claimed = user.get("streak_rewards_claimed", [])
    next_reward = get_next_streak_reward(streak, claimed)

    text = (
        f"👤 <b>Твой профиль</b>{premium_badge}\n\n"
        f"ID: <code>{user_id}</code>\n"
        f"Имя: {user['first_name']}\n"
        f"Premium: {'✅ Да' if premium_active else '❌ Нет'}\n"
        f"⚙️ Режим AI: {mode['icon']} <b>{mode['name']}</b>\n"
    )
    if ach_label:
        text += f"{ach_label}\n"
    text += f"\n{limit_block}\n"

    if next_reward:
        milestone, days = next_reward
        remaining_days = milestone - streak
        days_text = "навсегда" if days >= 36500 else f"{days} дн."
        text += f"\n🏆 До награды за {milestone} дней: <b>{remaining_days}</b> дн.\n⭐ Premium на {days_text}\n"

    text += (
        f"\n🏆 Ачивки: <b>{ach_count}/{ach_total}</b>\n"
        f"👥 Приглашено друзей: <b>{refs}</b>\n"
    )
    if gifts_count > 0:
        text += f"🎁 Подарено Premium: <b>{gifts_count}</b>\n"
    text += (
        f"📈 За всё время:\n"
        f"• Всего запросов: {user['total_requests']}\n"
        f"• С нами с: {user['registered_at'][:10]}"
    )

    buttons = []
    if not premium_active:
        buttons.append([InlineKeyboardButton(text="🎁 Получить бонус", callback_data="claim_bonus")])
        buttons.append([InlineKeyboardButton(text="🏆 Мои ачивки", callback_data="show_ach")])
        buttons.append([InlineKeyboardButton(text="⭐ Купить Premium", callback_data="show_premium")])
    else:
        buttons.append([InlineKeyboardButton(text="🏆 Мои ачивки", callback_data="show_ach")])
        buttons.append([InlineKeyboardButton(text="🎁 Подарить Premium", callback_data="gift_start")])

    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@dp.callback_query(F.data == "show_premium")
async def show_premium_cb(callback: CallbackQuery):
    await callback.answer()
    await cmd_premium(callback.message)


@dp.callback_query(F.data == "show_ach")
async def show_ach_cb(callback: CallbackQuery):
    await callback.answer()
    text = build_achievements_text(callback.from_user.id)
    await callback.message.answer(text)


@dp.message(Command("achivements"))
async def cmd_achivements(message: Message):
    text = build_achievements_text(message.from_user.id)
    await message.answer(text)


@dp.message(Command("reset"))
async def cmd_reset(message: Message):
    user_histories[message.from_user.id] = []
    if message.from_user.id in pending_states:
        del pending_states[message.from_user.id]
    await message.answer("🗑 <b>Диалог очищен</b>\n\nНачинаем заново!", reply_markup=get_main_menu(message.from_user.id))


@dp.message(Command("cancel"))
async def cmd_cancel(message: Message):
    if message.from_user.id in pending_states:
        del pending_states[message.from_user.id]
        await message.answer("❌ Отменено.", reply_markup=get_main_menu(message.from_user.id))
    else:
        await message.answer("Нечего отменять.", reply_markup=get_main_menu(message.from_user.id))


# ============ БОНУС ============
async def send_bonus_message(target, user_id, is_callback=False):
    user = get_user(user_id)
    if not user:
        msg = "Сначала напиши /start"
        if is_callback:
            await target.answer(msg, show_alert=True)
        else:
            await target.answer(msg)
        return
    if is_premium_active(user):
        msg = "⭐ У тебя Premium — безлимит! 🎉"
        if is_callback:
            await target.answer(msg, show_alert=True)
        else:
            await target.answer(msg)
        return
    success, status, streak = claim_daily_bonus(user_id)
    if not success:
        if status == "already":
            user = get_user(user_id)
            msg = (
                f"🎁 <b>Бонус уже получен сегодня!</b>\n\n"
                f"🔥 Стрик: <b>{user['bonus_streak']}</b> дней\n"
                f"📊 Лимит сегодня: <b>{get_effective_limit(user)}</b>\n\n"
                f"<i>Возвращайся завтра!</i>"
            )
        else:
            msg = status
        if is_callback:
            await target.answer("Уже получен", show_alert=True)
            await target.message.answer(msg)
        else:
            await target.answer(msg)
        return

    user = get_user(user_id)
    new_limit = get_effective_limit(user)
    fire = streak_fire(streak)
    msg = (
        f"🎁 <b>Бонус получен!</b>\n\n"
        f"🔥 Стрик: <b>{streak}</b> дней{fire}\n"
        f"📊 Лимит сегодня: <b>{new_limit}</b> запросов\n\n"
    )
    if streak < MAX_BONUS_DAYS:
        msg += "<i>Завтра зайдёшь — ещё +1 к лимиту!</i>"
    else:
        msg += f"<i>🏆 Стрик продолжает расти, но бонус максимум +{MAX_BONUS_DAYS}!</i>"

    new_ach = []
    if add_achievement(user_id, "first_bonus"):
        new_ach.append("first_bonus")
    new_ach += check_achievements(user_id)

    # Проверка наград за стрик
    streak_rewards = check_streak_rewards(user_id)

    if is_callback:
        await target.answer("Бонус получен! 🎁", show_alert=False)
        await target.message.answer(msg)
        await notify_new_achievements(target.message, new_ach)
        await notify_streak_rewards(target.message, streak_rewards)
    else:
        await target.answer(msg)
        await notify_new_achievements(target, new_ach)
        await notify_streak_rewards(target, streak_rewards)


@dp.message(Command("bonus"))
async def cmd_bonus(message: Message):
    await send_bonus_message(message, message.from_user.id, is_callback=False)


@dp.callback_query(F.data == "claim_bonus")
async def cb_claim_bonus(callback: CallbackQuery):
    await send_bonus_message(callback, callback.from_user.id, is_callback=True)


# ============ ЛИМИТ ============
async def check_limit_and_reply(message: Message) -> bool:
    allowed, remaining, effective_limit = check_and_increment_limit(message.from_user.id)
    if not allowed:
        await message.answer(
            f"⚠️ <b>Достигнут дневной лимит</b>\n\n"
            f"Ты использовал все <b>{effective_limit}</b> запросов на сегодня.\n"
            f"Лимит обновится завтра в 00:00.\n\n"
            f"🎁 <b>Заходи каждый день</b> — и лимит растёт!\n"
            f"👥 <b>Приглашай друзей</b> — получай запросы!\n"
            f"⭐ Или купи Premium — безлимит!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🎁 Бонус", callback_data="claim_bonus")],
                [InlineKeyboardButton(text="👥 Пригласить", callback_data="invite_friend")],
                [InlineKeyboardButton(text="⭐ Купить Premium", callback_data="show_premium")],
            ])
        )
        return False
    if remaining <= 3 and remaining > 0:
        await message.answer(f"💡 Осталось сегодня: <b>{remaining}</b>")
    return True


@dp.callback_query(F.data == "invite_friend")
async def cb_invite_friend(callback: CallbackQuery):
    await callback.answer()
    await cmd_invite(callback.message)


# ============ ПОДАРКИ ============
@dp.callback_query(F.data == "gift_start")
async def cb_gift_start(callback: CallbackQuery):
    user_id = callback.from_user.id
    pending_states[user_id] = {"action": "gift_waiting_username"}
    await callback.answer()
    await callback.message.answer(
        "🎁 <b>Подарок Premium</b>\n\n"
        "Кому подарить? Отправь:\n"
        "• <b>@username</b> друга (например: <code>@vasya</code>)\n"
        "• или его <b>ID</b> (например: <code>123456789</code>)\n\n"
        "❌ Отмена: /cancel"
    )


@dp.callback_query(F.data == "gift_cancel")
async def cb_gift_cancel(callback: CallbackQuery):
    if callback.from_user.id in pending_states:
        del pending_states[callback.from_user.id]
    await callback.answer()
    try:
        await callback.message.edit_text("❌ Подарок отменён.")
    except Exception:
        await callback.message.answer("❌ Подарок отменён.")


@dp.callback_query(F.data.startswith("giftbuy_"))
async def cb_gift_buy(callback: CallbackQuery):
    user_id = callback.from_user.id
    state = pending_states.get(user_id)
    if not state or state.get("action") != "gift_select_plan":
        await callback.answer("Сессия истекла. Начни заново.", show_alert=True)
        return
    plan_key = callback.data.replace("giftbuy_", "")
    plan = PREMIUM_PLANS.get(plan_key)
    if not plan:
        await callback.answer("Ошибка тарифа", show_alert=True)
        return
    to_user_id = state.get("to_user_id")
    if not to_user_id:
        await callback.answer("Ошибка получателя", show_alert=True)
        return
    await callback.answer()
    target = get_user(to_user_id)
    if not target:
        await callback.message.answer("❌ Получатель не найден.")
        del pending_states[user_id]
        return
    if to_user_id == user_id:
        await callback.message.answer("❌ Нельзя подарить Premium самому себе!")
        del pending_states[user_id]
        return
    try:
        await bot.send_invoice(
            chat_id=user_id,
            title=f"🎁 Подарок: {plan['title']}",
            description=f"Для: {target['first_name']} (@{target['username'] or 'нет'})",
            payload=f"gift_{plan_key}_{to_user_id}",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label=plan['title'], amount=plan['price'])],
            start_parameter="gift"
        )
        del pending_states[user_id]
    except Exception as e:
        logger.error(f"Gift invoice error: {e}")
        await callback.message.answer("⚠️ Не удалось создать счёт.")


async def handle_gift_username(message: Message, state: dict) -> bool:
    user_id = message.from_user.id
    text = message.text.strip()
    target_id = None
    if text.startswith("@") or not text.isdigit():
        username = text.lstrip("@").lower()
        target_id = find_user_by_username(username)
        if not target_id:
            await message.answer(
                f"❌ <b>@{username}</b> не найден в боте.\n\n"
                f"<b>Что делать:</b>\n"
                f"1. Отправь другу ссылку: <code>t.me/logiMind_HomeworkBot</code>\n"
                f"2. Пусть он напишет /start\n"
                f"3. Потом возвращайся и снова подари 🎁\n\n"
                f"<i>Или отправь ID друга (число).</i>\n"
                f"<i>Отмена: /cancel</i>"
            )
            return True
    elif text.isdigit():
        target_id = int(text)
        target_user = get_user(target_id)
        if not target_user:
            await message.answer(f"❌ Юзер с ID <code>{target_id}</code> не найден.\n\n<i>Отмена: /cancel</i>")
            return True
    if target_id == user_id:
        await message.answer("❌ Нельзя подарить Premium самому себе!")
        del pending_states[user_id]
        return True
    target_user = get_user(target_id)
    if not target_user:
        await message.answer("❌ Получатель не найден.")
        del pending_states[user_id]
        return True
    pending_states[user_id] = {"action": "gift_select_plan", "to_user_id": target_id}
    await message.answer(
        f"🎁 <b>Подарок для:</b> {target_user['first_name']} (@{target_user['username'] or 'нет'})\n\n<b>Выбери тариф 👇</b>",
        reply_markup=get_gift_plans_keyboard()
    )
    return True


# ============ ФОТО ============
@dp.message(F.photo)
async def handle_photo(message: Message):
    user = message.from_user
    create_or_update_user(user.id, user.username, user.first_name)
    # Сброс ожидания подарка
    if message.from_user.id in pending_states:
        del pending_states[message.from_user.id]
    if not await check_limit_and_reply(message):
        return
    caption = message.caption or ""
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    try:
        photo = message.photo[-1]
        file = await bot.get_file(photo.file_id)
        file_bytes = await bot.download_file(file.file_path)
        image_base64 = base64.b64encode(file_bytes.read()).decode("utf-8")
        answer = await ask_ai_vision(user.id, image_base64, caption)
        if len(answer) <= 4000:
            await message.answer(answer)
        else:
            for i in range(0, len(answer), 4000):
                await message.answer(answer[i:i+4000])
        new_ach = []
        if add_achievement(user.id, "first_photo"):
            new_ach.append("first_photo")
        new_ach += check_achievements(user.id)
        await notify_new_achievements(message, new_ach)
    except Exception as e:
        logger.error(f"Photo error: {e}")
        await message.answer("⚠️ Не смог обработать фото.")


# ============ ТЕКСТ ============
@dp.message(F.text)
async def handle_text(message: Message):
    user = message.from_user
    create_or_update_user(user.id, user.username, user.first_name)
    text = message.text.strip()

    # Игнорируем команды
    if text.startswith("/"):
        from aiogram.dispatcher.event.bases import SkipHandler
        raise SkipHandler()

    # Кнопки меню сбрасывают ожидание подарка
    menu_buttons = [
        "🤖 Спросить AI", "🎁 Бонус", "📚 Помощь с ДЗ", "👤 Профиль",
        "🥇 Топ", "🔥 Стрики", "⭐ Premium", "⚙️ Режим AI", "👥 Пригласить",
        "👑 БОСС-ПАНЕЛЬ", "❓ Помощь"
    ]
    if text in menu_buttons:
        if message.from_user.id in pending_states:
            del pending_states[message.from_user.id]

    # Проверка ожидания @username
    if message.from_user.id in pending_states:
        state = pending_states[message.from_user.id]
        if state.get("action") == "gift_waiting_username":
            if not (text.startswith("@") or text.isdigit()):
                del pending_states[message.from_user.id]
                await message.answer(
                    "❌ <b>Не похоже на @username или ID.</b>\n\n"
                    "Отмена. Нажми «⭐ Premium» → «🎁 Подарить другу» чтобы попробовать снова."
                )
                return
            handled = await handle_gift_username(message, state)
            if handled:
                return

    if text == "🤖 Спросить AI":
        await message.answer("🤖 Напиши свой вопрос или пришли фото!")
        return
    elif text == "🎁 Бонус":
        await cmd_bonus(message)
        return
    elif text == "📚 Помощь с ДЗ":
        await message.answer("📚 Напиши задание или сфотографируй его 📷")
        return
    elif text == "👤 Профиль":
        await cmd_profile(message)
        return
    elif text == "🥇 Топ":
        await cmd_top(message)
        return
    elif text == "🔥 Стрики":
        await cmd_top_streaks(message)
        return
    elif text == "⭐ Premium":
        await cmd_premium(message)
        return
    elif text == "⚙️ Режим AI":
        await cmd_mode(message)
        return
    elif text == "👥 Пригласить":
        await cmd_invite(message)
        return
    elif text == "👑 БОСС-ПАНЕЛЬ":
        await cmd_boss(message)
        return
    elif text == "❓ Помощь":
        await cmd_help(message)
        return

    if len(text) < 2:
        return
    if len(text) > 4000:
        await message.answer("⚠️ Слишком длинное сообщение.")
        return
    if not await check_limit_and_reply(message):
        return

    user_data = get_user(user.id)
    is_prem = is_premium_active(user_data) if user_data else False
    mode_key = user_data.get("ai_mode", "teacher") if user_data else "teacher"

    await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    answer = await ask_ai(user.id, text, is_prem, mode_key)

    if len(answer) <= 4000:
        await message.answer(answer)
    else:
        for i in range(0, len(answer), 4000):
            await message.answer(answer[i:i+4000])

    new_ach = check_achievements(user.id)
    await notify_new_achievements(message, new_ach)


# ============ ОПЛАТА ============
@dp.callback_query(F.data.startswith("buy_"))
async def handle_buy(callback: CallbackQuery):
    plan_key = callback.data.replace("buy_", "")
    plan = PREMIUM_PLANS.get(plan_key)
    if not plan:
        await callback.answer("Ошибка.", show_alert=True)
        return
    await callback.answer()
    try:
        await bot.send_invoice(
            chat_id=callback.from_user.id,
            title=plan["title"],
            description=plan["description"],
            payload=f"premium_{plan_key}",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label=plan["title"], amount=plan["price"])],
            start_parameter="premium"
        )
    except Exception as e:
        logger.error(f"Invoice error: {e}")
        await callback.message.answer("⚠️ Не удалось создать счёт.")


@dp.pre_checkout_query()
async def pre_checkout(q: PreCheckoutQuery):
    await q.answer(ok=True)


@dp.message(F.successful_payment)
async def on_payment(message: Message):
    user = message.from_user
    payment = message.successful_payment
    payload = payment.invoice_payload

    if payload.startswith("gift_"):
        parts = payload.split("_")
        if len(parts) < 3:
            await message.answer("⚠️ Ошибка данных подарка.")
            return
        plan_key = parts[1]
        try:
            to_user_id = int(parts[2])
        except ValueError:
            await message.answer("⚠️ Ошибка получателя.")
            return
        plan = PREMIUM_PLANS.get(plan_key)
        if not plan:
            await message.answer("⚠️ Ошибка тарифа.")
            return
        ok, until = create_gift(user.id, to_user_id, plan_key, plan["price"])
        if not ok:
            await message.answer("⚠️ Не удалось активировать подарок.")
            return
        target = get_user(to_user_id)
        target_name = target["first_name"] if target else "друг"
        until_text = "навсегда" if plan["days"] >= 36500 else f"до {until.strftime('%d.%m.%Y')}"
        await message.answer(
            f"🎉 <b>Подарок отправлен!</b>\n\n"
            f"👤 Получатель: <b>{target_name}</b>\n"
            f"📦 {plan['title']}\n"
            f"📅 Premium активен {until_text}\n\n"
            f"Спасибо за щедрость! 💝"
        )
        try:
            await bot.send_message(
                to_user_id,
                f"🎁 <b>ТЕБЕ ПОДАРИЛИ PREMIUM!</b>\n\n"
                f"👤 От: {user.first_name} (@{user.username or 'нет'})\n"
                f"📦 {plan['title']}\n"
                f"📅 Активен {until_text}\n\n"
                f"Спасибо другу и приятного использования! 🚀"
            )
        except Exception as e:
            logger.error(f"Не уведомил получателя: {e}")
        try:
            await bot.send_message(
                OWNER_ID,
                f"🎁 <b>ПОДАРОК PREMIUM!</b>\n\n"
                f"👤 От: {user.first_name} (@{user.username or 'нет'}) <code>{user.id}</code>\n"
                f"👥 Кому: {target_name} <code>{to_user_id}</code>\n"
                f"📦 {plan['title']}\n"
                f"⭐ <b>{plan['price']} звёзд</b>"
            )
        except Exception:
            pass
        new_ach = check_gift_achievements(user.id)
        for key in new_ach:
            ach = ACHIEVEMENTS.get(key)
            if ach:
                await message.answer(
                    f"🎉 <b>НОВАЯ АЧИВКА!</b>\n\n"
                    f"{ach['icon']} <b>{ach['name']}</b>\n"
                    f"<i>{ach['desc']}</i>"
                )
        return

    plan_key = payload.replace("premium_", "")
    plan = PREMIUM_PLANS.get(plan_key)
    if not plan:
        await message.answer("⚠️ Ошибка тарифа.")
        return
    until = activate_premium(user.id, plan["days"])
    logger.info(f"💰 Оплата! {user.id} купил {plan_key} за {plan['price']}")
    until_text = "навсегда" if plan["days"] >= 36500 else f"до {until.strftime('%d.%m.%Y')}"
    await message.answer(
        f"🎉 <b>Спасибо за покупку!</b>\n\n"
        f"⭐ <b>Premium активирован</b> {until_text}\n\n"
        f"Теперь у тебя безлимит запросов! 🚀"
    )
    if add_achievement(user.id, "premium"):
        await message.answer(
            f"🎉 <b>НОВАЯ АЧИВКА!</b>\n\n"
            f"{ACHIEVEMENTS['premium']['icon']} <b>{ACHIEVEMENTS['premium']['name']}</b>\n"
            f"<i>{ACHIEVEMENTS['premium']['desc']}</i>"
        )
    try:
        await bot.send_message(
            OWNER_ID,
            f"💰 <b>НОВАЯ ОПЛАТА!</b>\n\n"
            f"👤 {user.first_name} (@{user.username or 'нет'})\n"
            f"🆔 <code>{user.id}</code>\n"
            f"📦 {plan['title']}\n"
            f"⭐ <b>{plan['price']} звёзд</b>\n"
            f"📅 {until_text}"
        )
    except Exception as e:
        logger.error(f"Не уведомил владельца: {e}")


# ============================================================
# ============ 👑 БОСС-ПАНЕЛЬ (ТОЛЬКО ДЛЯ ТЕБЯ) ============
# ============================================================

def boss_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="b_stats"),
         InlineKeyboardButton(text="👥 Юзеры", callback_data="b_users")],
        [InlineKeyboardButton(text="⭐ Premium", callback_data="b_premium"),
         InlineKeyboardButton(text="🔥 Стрики", callback_data="b_streaks")],
        [InlineKeyboardButton(text="🎁 Бонус", callback_data="b_bonus"),
         InlineKeyboardButton(text="📢 Реклама", callback_data="b_ads")],
        [InlineKeyboardButton(text="🏆 Ачивки", callback_data="b_ach"),
         InlineKeyboardButton(text="💎 Топ юзеров", callback_data="b_top")],
        [InlineKeyboardButton(text="🎫 Промокоды", callback_data="b_promos"),
         InlineKeyboardButton(text="📖 Все команды", callback_data="b_all_cmds")],
        [InlineKeyboardButton(text="❌ Закрыть", callback_data="b_close")],
    ])


def build_boss_panel_text():
    stats = get_stats()
    return (
        f"👑 <b>БОСС-ПАНЕЛЬ logiMind</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 Юзеров: <b>{stats['total_users']}</b>\n"
        f"⭐ Premium: <b>{stats['premium_users']}</b>\n"
        f"🔥 Активных 24ч: <b>{stats['active_24h']}</b>\n"
        f"🔥 Со стриком 7+: <b>{stats['streak_7']}</b>\n\n"
        f"📊 Запросов сегодня: <b>{stats['today_requests']}</b>\n"
        f"📈 Запросов всего: <b>{stats['total_requests']}</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>Быстрые команды:</b>\n"
        f"/users — список юзеров\n"
        f"/user 123 — инфо о юзере\n"
        f"/give_premium 123 30\n"
        f"/give_streak 123 50\n"
        f"/give_ach 123 key\n"
        f"/reset_limit 123\n"
        f"/broadcast текст\n\n"
        f"<i>Полный список: 📖 Все команды</i>"
    )


def build_all_commands_text():
    return (
        "📖 <b>ВСЕ КОМАНДЫ БОССА</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📊 <b>ОСНОВНЫЕ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "/boss — БОСС-ПАНЕЛЬ\n"
        "/me — мой ID\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "👥 <b>ЮЗЕРЫ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "/users — список юзеров\n"
        "/user &lt;id&gt; — инфо о юзере\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "⭐ <b>PREMIUM</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "/give_premium &lt;id&gt; &lt;days&gt;\n"
        "/take_premium &lt;id&gt;\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🔥 <b>СТРИКИ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "/give_streak &lt;id&gt; &lt;value&gt;\n"
        "/take_streak &lt;id&gt;\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🏆 <b>АЧИВКИ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "/give_ach &lt;id&gt; &lt;key&gt;\n"
        "/take_ach &lt;id&gt; &lt;key&gt;\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📊 <b>ЛИМИТЫ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "/reset_limit &lt;id&gt;\n"
        "/reset_bonus &lt;id&gt;\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🎫 <b>ПРОМОКОДЫ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "/create_promo &lt;код&gt; &lt;тип&gt; &lt;значение&gt; [лимит] [дней]\n"
        "  тип: premium / requests / streak\n"
        "/promos — список промокодов\n"
        "/promo_info &lt;код&gt; — инфо\n"
        "/promo_delete &lt;код&gt; — удалить\n\n"
        "Примеры:\n"
        "<code>/create_promo NEWYEAR premium 30 100 7</code>\n"
        "<code>/create_promo HAPPY requests 100 0 30</code>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📢 <b>РЕКЛАМА</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "/add_my_ad &lt;название&gt; | &lt;ссылка&gt; | &lt;показов&gt;\n"
        "/list_ads — список реклам\n"
        "/ad_info &lt;id&gt; — инфо\n"
        "/ad_pause &lt;id&gt; — пауза\n"
        "/ad_resume &lt;id&gt; — снять паузу\n"
        "/ad_delete &lt;id&gt; — удалить\n"
        "/ad_stats — статистика\n\n"
        "Пример:\n"
        "<code>/add_my_ad Мой канал | t.me/mychannel | 5000</code>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📢 <b>ПРОЧЕЕ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "/broadcast &lt;текст&gt; — рассылка\n"
    )


@dp.message(Command("boss"))
async def cmd_boss(message: Message):
    if message.from_user.id != OWNER_ID:
        await message.answer("⛔ <b>Эта команда только для БОССА</b>")
        return
    await message.answer(build_boss_panel_text(), reply_markup=boss_keyboard())


@dp.callback_query(F.data.startswith("b_"))
async def cb_boss(callback: CallbackQuery):
    if callback.from_user.id != OWNER_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return
    action = callback.data
    if action == "b_close":
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.answer()
        return
    if action == "b_users":
        await callback.answer()
        await show_users_list(callback.message)
    elif action == "b_stats":
        await callback.answer()
        await callback.message.answer(build_boss_panel_text(), reply_markup=boss_keyboard())
    elif action == "b_all_cmds":
        await callback.answer()
        await callback.message.answer(build_all_commands_text())
    elif action == "b_ach":
        await callback.answer()
        text = "🏆 <b>Все ачивки и ключи:</b>\n\n"
        for key, ach in ACHIEVEMENTS.items():
            text += f"{ach['icon']} <code>{key}</code> — {ach['name']}\n"
        text += "\n<b>Выдать:</b> /give_ach 123 first_step\n<b>Забрать:</b> /take_ach 123 first_step"
        await callback.message.answer(text)
    elif action == "b_premium":
        await callback.answer()
        await callback.message.answer(
            "⭐ <b>Управление Premium</b>\n\n"
            "/give_premium &lt;user_id&gt; &lt;days&gt;\n"
            "/take_premium &lt;user_id&gt;\n\n"
            "Пример: <code>/give_premium 123456 30</code>"
        )
    elif action == "b_streaks":
        await callback.answer()
        await callback.message.answer(
            "🔥 <b>Управление стриками</b>\n\n"
            "/give_streak &lt;user_id&gt; &lt;value&gt;\n"
            "/take_streak &lt;user_id&gt;\n\n"
            "Пример: <code>/give_streak 123456 50</code>"
        )
    elif action == "b_bonus":
        await callback.answer()
        await callback.message.answer(
            "🎁 <b>Бонус</b>\n\n"
            "/reset_bonus &lt;user_id&gt; — юзер сможет взять бонус заново\n\n"
            "Пример: <code>/reset_bonus 123456</code>"
        )
    elif action == "b_promos":
        await callback.answer()
        await callback.message.answer(
            "🎫 <b>Промокоды</b>\n\n"
            "<b>Создать:</b>\n"
            "/create_promo &lt;код&gt; &lt;тип&gt; &lt;значение&gt; [лимит] [дней]\n\n"
            "<b>Типы:</b>\n"
            "• premium — Premium на N дней\n"
            "• requests — +N запросов\n"
            "• streak — +N к стрику\n\n"
            "<b>Примеры:</b>\n"
            "<code>/create_promo NEWYEAR premium 30 100 7</code>\n"
            "<code>/create_promo HAPPY requests 100 0 30</code>\n\n"
            "<b>Управление:</b>\n"
            "/promos — список\n"
            "/promo_info &lt;код&gt;\n"
            "/promo_delete &lt;код&gt;"
        )
    elif action == "b_ads":
        await callback.answer()
        await callback.message.answer(
            "📢 <b>Реклама</b>\n\n"
            "<b>Добавить свою рекламу:</b>\n"
            "/add_my_ad &lt;название&gt; | &lt;ссылка&gt; | &lt;показов&gt;\n\n"
            "<b>Пример:</b>\n"
            "<code>/add_my_ad Мой канал | t.me/mychannel | 5000</code>\n\n"
            "<b>Управление:</b>\n"
            "/list_ads — список\n"
            "/ad_info &lt;id&gt;\n"
            "/ad_pause &lt;id&gt;\n"
            "/ad_resume &lt;id&gt;\n"
            "/ad_delete &lt;id&gt;\n"
            "/ad_stats — статистика"
        )
    elif action == "b_top":
        await callback.answer()
        top_text = build_top_text(today=False)
        top_kb = get_top_keyboard(today=False)
        await callback.message.answer(top_text, reply_markup=top_kb)


# ============ АДМИН-КОМАНДЫ ============
async def show_users_list(message: Message):
    rows = get_recent_users(limit=20)
    if not rows:
        await message.answer("Пока никого нет.")
        return
    text = "👥 <b>Последние 20 юзеров</b>\n\n"
    for row in rows:
        uid, fname, uname, reg, total, prem, streak = row
        prem_icon = "⭐ " if prem else ""
        fire = streak_fire(streak)
        text += f"{prem_icon}<code>{uid}</code> — {fname or 'Аноним'} ({total} зап.){fire}\n"
    await message.answer(text)


@dp.message(Command("users"))
async def cmd_users(message: Message):
    if message.from_user.id != OWNER_ID:
        await message.answer("⛔ Нет доступа.")
        return
    await show_users_list(message)


@dp.message(Command("user"))
async def cmd_user(message: Message):
    if message.from_user.id != OWNER_ID:
        await message.answer("⛔ Нет доступа.")
        return
    args = message.text.split()
    if len(args) != 2:
        await message.answer("Использование: <code>/user 123456789</code>")
        return
    try:
        target_id = int(args[1])
    except ValueError:
        await message.answer("ID должен быть числом.")
        return
    u = get_user(target_id)
    if not u:
        await message.answer(f"❌ Юзер <code>{target_id}</code> не найден.")
        return
    prem_active = is_premium_active(u)
    until_str = "-"
    if u["premium_until"]:
        try:
            until_str = datetime.fromisoformat(u["premium_until"]).strftime('%d.%m.%Y')
        except Exception:
            pass
    gifts_count = count_gifts_from(target_id)
    mode_key = u.get("ai_mode", "teacher")
    mode = AI_MODES.get(mode_key, AI_MODES["teacher"])
    text = (
        f"👤 <b>Юзер {target_id}</b>\n\n"
        f"Имя: {u['first_name']}\n"
        f"Username: @{u['username'] or 'нет'}\n"
        f"Регистрация: {u['registered_at'][:10]}\n"
        f"Premium: {'✅ Да' if prem_active else '❌ Нет'}\n"
        f"Premium до: {until_str}\n"
        f"Режим AI: {mode['icon']} {mode['name']}\n"
        f"Стрик: {u['bonus_streak']} {streak_fire(u['bonus_streak'])}\n"
        f"Запросов сегодня: {u['requests_today']}\n"
        f"Запросов всего: {u['total_requests']}\n"
        f"Ачивок: {len(u['achievements'])}\n"
        f"Рефералов: {u.get('referrals_count', 0)}\n"
        f"Подарено Premium: {gifts_count}\n"
    )
    await message.answer(text)


@dp.message(Command("give_premium"))
async def cmd_give_premium(message: Message):
    if message.from_user.id != OWNER_ID:
        await message.answer("⛔ Нет доступа.")
        return
    args = message.text.split()
    if len(args) != 3:
        await message.answer("Использование: <code>/give_premium 123456 30</code>")
        return
    try:
        target_id = int(args[1]); days = int(args[2])
    except ValueError:
        await message.answer("ID и дни — числа.")
        return
    u = get_user(target_id)
    if not u:
        await message.answer(f"❌ Юзер <code>{target_id}</code> не найден.")
        return
    until = activate_premium(target_id, days)
    add_achievement(target_id, "premium")
    await message.answer(f"✅ Premium выдан <code>{target_id}</code> до {until.strftime('%d.%m.%Y')}")
    try:
        await bot.send_message(target_id, f"🎁 <b>Тебе выдан Premium на {days} дней!</b>\n\nСпасибо что с нами 🚀")
    except Exception:
        pass


@dp.message(Command("take_premium"))
async def cmd_take_premium(message: Message):
    if message.from_user.id != OWNER_ID:
        await message.answer("⛔ Нет доступа.")
        return
    args = message.text.split()
    if len(args) != 2:
        await message.answer("Использование: <code>/take_premium 123456</code>")
        return
    try:
        target_id = int(args[1])
    except ValueError:
        await message.answer("ID — число.")
        return
    deactivate_premium(target_id)
    await message.answer(f"✅ Premium забран у <code>{target_id}</code>")


@dp.message(Command("give_streak"))
async def cmd_give_streak(message: Message):
    if message.from_user.id != OWNER_ID:
        await message.answer("⛔ Нет доступа.")
        return
    args = message.text.split()
    if len(args) != 3:
        await message.answer("Использование: <code>/give_streak 123456 50</code>")
        return
    try:
        target_id = int(args[1]); value = int(args[2])
    except ValueError:
        await message.answer("ID и значение — числа.")
        return
    u = get_user(target_id)
    if not u:
        await message.answer(f"❌ Юзер <code>{target_id}</code> не найден.")
        return
    set_streak_admin(target_id, value)
    check_achievements(target_id)
    await message.answer(f"✅ Стрик <code>{target_id}</code> = {value} {streak_fire(value)}")


@dp.message(Command("take_streak"))
async def cmd_take_streak(message: Message):
    if message.from_user.id != OWNER_ID:
        await message.answer("⛔ Нет доступа.")
        return
    args = message.text.split()
    if len(args) != 2:
        await message.answer("Использование: <code>/take_streak 123456</code>")
        return
    try:
        target_id = int(args[1])
    except ValueError:
        await message.answer("ID — число.")
        return
    set_streak_admin(target_id, 0)
    await message.answer(f"✅ Стрик <code>{target_id}</code> обнулён")


@dp.message(Command("give_ach"))
async def cmd_give_ach(message: Message):
    if message.from_user.id != OWNER_ID:
        await message.answer("⛔ Нет доступа.")
        return
    args = message.text.split()
    if len(args) != 3:
        await message.answer("Использование: <code>/give_ach 123456 first_step</code>")
        return
    try:
        target_id = int(args[1])
    except ValueError:
        await message.answer("ID — число.")
        return
    key = args[2]
    if key not in ACHIEVEMENTS:
        await message.answer(f"❌ Ачивка <code>{key}</code> не существует.")
        return
    if add_achievement(target_id, key):
        ach = ACHIEVEMENTS[key]
        await message.answer(f"✅ Выдана ачивка {ach['icon']} <b>{ach['name']}</b> юзеру <code>{target_id}</code>")
        try:
            await bot.send_message(target_id, f"🎉 <b>НОВАЯ АЧИВКА!</b>\n\n{ach['icon']} <b>{ach['name']}</b>\n<i>{ach['desc']}</i>")
        except Exception:
            pass
    else:
        await message.answer("⚠️ У юзера уже есть эта ачивка")


@dp.message(Command("take_ach"))
async def cmd_take_ach(message: Message):
    if message.from_user.id != OWNER_ID:
        await message.answer("⛔ Нет доступа.")
        return
    args = message.text.split()
    if len(args) != 3:
        await message.answer("Использование: <code>/take_ach 123456 first_step</code>")
        return
    try:
        target_id = int(args[1])
    except ValueError:
        await message.answer("ID — число.")
        return
    key = args[2]
    u = get_user(target_id)
    if not u:
        await message.answer(f"❌ Юзер <code>{target_id}</code> не найден.")
        return
    if key not in u["achievements"]:
        await message.answer("⚠️ У юзера нет этой ачивки")
        return
    ach_list = [a for a in u["achievements"] if a != key]
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET achievements = ? WHERE user_id = ?", (json.dumps(ach_list), target_id))
    conn.commit()
    conn.close()
    await message.answer(f"✅ Ачивка <code>{key}</code> забрана у <code>{target_id}</code>")


@dp.message(Command("reset_limit"))
async def cmd_reset_limit(message: Message):
    if message.from_user.id != OWNER_ID:
        await message.answer("⛔ Нет доступа.")
        return
    args = message.text.split()
    if len(args) != 2:
        await message.answer("Использование: <code>/reset_limit 123456</code>")
        return
    try:
        target_id = int(args[1])
    except ValueError:
        await message.answer("ID — число.")
        return
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET requests_today = 0 WHERE user_id = ?", (target_id,))
    conn.commit()
    conn.close()
    await message.answer(f"✅ Лимит сброшен <code>{target_id}</code>")


@dp.message(Command("reset_bonus"))
async def cmd_reset_bonus(message: Message):
    if message.from_user.id != OWNER_ID:
        await message.answer("⛔ Нет доступа.")
        return
    args = message.text.split()
    if len(args) != 2:
        await message.answer("Использование: <code>/reset_bonus 123456</code>")
        return
    try:
        target_id = int(args[1])
    except ValueError:
        await message.answer("ID — число.")
        return
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET last_bonus_date = NULL WHERE user_id = ?", (target_id,))
    conn.commit()
    conn.close()
    await message.answer(f"✅ Бонус сброшен — юзер <code>{target_id}</code> может получить заново")


@dp.message(Command("broadcast"))
async def cmd_broadcast(message: Message):
    if message.from_user.id != OWNER_ID:
        await message.answer("⛔ Нет доступа.")
        return
    text = message.text.replace("/broadcast", "", 1).strip()
    if not text:
        await message.answer("Использование: <code>/broadcast текст</code>")
        return
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = [row[0] for row in cursor.fetchall()]
    conn.close()
    await message.answer(f"📢 Начинаю рассылку на {len(users)} юзеров...")
    success = 0
    failed = 0
    for uid in users:
        try:
            await bot.send_message(uid, f"📢 <b>Сообщение от админа:</b>\n\n{text}")
            success += 1
            await asyncio.sleep(0.05)
        except Exception:
            failed += 1
    await message.answer(f"✅ Рассылка завершена\n\n📤 Отправлено: {success}\n❌ Ошибок: {failed}")


@dp.message(Command("me"))
async def cmd_me(message: Message):
    await message.answer(f"🆔 Твой ID: <code>{message.from_user.id}</code>")


# ============ ПРОМОКОДЫ (команды админа) ============
@dp.message(Command("create_promo"))
async def cmd_create_promo(message: Message):
    if message.from_user.id != OWNER_ID:
        await message.answer("⛔ Нет доступа.")
        return
    args = message.text.split()
    if len(args) < 4:
        await message.answer(
            "📝 <b>Создание промокода</b>\n\n"
            "Использование:\n"
            "<code>/create_promo КОД ТИП ЗНАЧЕНИЕ [ЛИМИТ] [ДНЕЙ]</code>\n\n"
            "<b>Типы:</b> premium / requests / streak\n\n"
            "<b>Примеры:</b>\n"
            "<code>/create_promo NEWYEAR premium 30 100 7</code>\n"
            "<code>/create_promo HAPPY requests 100 0 30</code>"
        )
        return
    code = args[1].upper()
    promo_type = args[2].lower()
    try:
        value = int(args[3])
    except ValueError:
        await message.answer("❌ Значение должно быть числом.")
        return
    max_uses = 0
    days_valid = 0
    if len(args) >= 5:
        try:
            max_uses = int(args[4])
        except ValueError:
            pass
    if len(args) >= 6:
        try:
            days_valid = int(args[5])
        except ValueError:
            pass

    if promo_type not in ("premium", "requests", "streak"):
        await message.answer("❌ Тип должен быть: premium / requests / streak")
        return

    ok = create_promo(code, promo_type, value, max_uses, days_valid, message.from_user.id)
    if not ok:
        await message.answer(f"❌ Промокод <code>{code}</code> уже существует.")
        return

    type_names = {"premium": "Premium", "requests": "запросов", "streak": "к стрику"}
    info = (
        f"✅ <b>Промокод создан!</b>\n\n"
        f"🎫 Код: <code>{code}</code>\n"
        f"📦 Тип: {type_names[promo_type]}\n"
        f"🔢 Значение: {value}\n"
    )
    if max_uses > 0:
        info += f"👥 Лимит: {max_uses} активаций\n"
    else:
        info += f"👥 Лимит: без ограничений\n"
    if days_valid > 0:
        info += f"📅 Действует: {days_valid} дней\n"
    else:
        info += f"📅 Действует: бессрочно\n"
    await message.answer(info)


@dp.message(Command("promos"))
async def cmd_promos(message: Message):
    if message.from_user.id != OWNER_ID:
        await message.answer("⛔ Нет доступа.")
        return
    rows = list_promos()
    if not rows:
        await message.answer("🎫 Промокодов нет.")
        return
    text = "🎫 <b>ВСЕ ПРОМОКОДЫ</b>\n\n"
    for row in rows[:20]:
        code, ptype, val, max_u, used, exp, created, _ = row
        exp_str = "бессрочно"
        if exp:
            try:
                exp_str = datetime.fromisoformat(exp).strftime('%d.%m.%Y')
            except Exception:
                pass
        limit_str = f"{used}/{max_u}" if max_u > 0 else f"{used}"
        text += f"<code>{code}</code> — {ptype} {val} — {limit_str} — до {exp_str}\n"
    await message.answer(text)


@dp.message(Command("promo_info"))
async def cmd_promo_info(message: Message):
    if message.from_user.id != OWNER_ID:
        await message.answer("⛔ Нет доступа.")
        return
    args = message.text.split()
    if len(args) != 2:
        await message.answer("Использование: <code>/promo_info КОД</code>")
        return
    promo = get_promo(args[1])
    if not promo:
        await message.answer("❌ Промокод не найден.")
        return
    exp_str = "бессрочно"
    if promo["expires_at"]:
        try:
            exp_str = datetime.fromisoformat(promo["expires_at"]).strftime('%d.%m.%Y')
        except Exception:
            pass
    limit_str = f"{promo['used_count']}/{promo['max_uses']}" if promo["max_uses"] > 0 else f"{promo['used_count']} (без лимита)"
    text = (
        f"🎫 <b>Промокод {promo['code']}</b>\n\n"
        f"📦 Тип: {promo['promo_type']}\n"
        f"🔢 Значение: {promo['value']}\n"
        f"📊 Активаций: {limit_str}\n"
        f"📅 До: {exp_str}\n"
    )
    await message.answer(text)


@dp.message(Command("promo_delete"))
async def cmd_promo_delete(message: Message):
    if message.from_user.id != OWNER_ID:
        await message.answer("⛔ Нет доступа.")
        return
    args = message.text.split()
    if len(args) != 2:
        await message.answer("Использование: <code>/promo_delete КОД</code>")
        return
    delete_promo(args[1])
    await message.answer(f"✅ Промокод <code>{args[1].upper()}</code> удалён")


# ============ РЕКЛАМА (команды админа) ============
@dp.message(Command("add_my_ad"))
async def cmd_add_my_ad(message: Message):
    if message.from_user.id != OWNER_ID:
        await message.answer("⛔ Нет доступа.")
        return
    text = message.text.replace("/add_my_ad", "", 1).strip()
    parts = [p.strip() for p in text.split("|")]
    if len(parts) != 3:
        await message.answer(
            "📝 <b>Добавление своей рекламы</b>\n\n"
            "Использование:\n"
            "<code>/add_my_ad Название | ссылка | показов</code>\n\n"
            "Пример:\n"
            "<code>/add_my_ad Мой канал | t.me/mychannel | 5000</code>"
        )
        return
    title, link, views_str = parts
    try:
        total_views = int(views_str)
    except ValueError:
        await message.answer("❌ Показов должно быть число.")
        return
    add_ad(message.from_user.id, title, link, "", total_views, "custom", 0)
    await message.answer(
        f"✅ <b>Реклама добавлена!</b>\n\n"
        f"📢 {title}\n"
        f"🔗 {link}\n"
        f"👁 Показов: {total_views}"
    )


@dp.message(Command("list_ads"))
async def cmd_list_ads(message: Message):
    if message.from_user.id != OWNER_ID:
        await message.answer("⛔ Нет доступа.")
        return
    rows = list_ads()
    if not rows:
        await message.answer("📢 Рекламы нет.")
        return
    text = "📢 <b>ВСЕ РЕКЛАМЫ</b>\n\n"
    for row in rows[:20]:
        ad_id, uid, title, link, desc, total, current, pkg, price, status, created = row
        status_icon = {"active": "🟢", "paused": "⏸", "finished": "✅"}.get(status, "❓")
        text += f"{status_icon} <b>#{ad_id}</b> {title}\n"
        text += f"   👁 {current}/{total} — {status}\n\n"
    await message.answer(text)


@dp.message(Command("ad_info"))
async def cmd_ad_info(message: Message):
    if message.from_user.id != OWNER_ID:
        await message.answer("⛔ Нет доступа.")
        return
    args = message.text.split()
    if len(args) != 2:
        await message.answer("Использование: <code>/ad_info ID</code>")
        return
    try:
        ad_id = int(args[1])
    except ValueError:
        await message.answer("ID должен быть числом.")
        return
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM ads WHERE id = ?", (ad_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        await message.answer("❌ Реклама не найдена.")
        return
    ad_id, uid, title, link, desc, total, current, pkg, price, status, created = row
    text = (
        f"📢 <b>Реклама #{ad_id}</b>\n\n"
        f"📝 {title}\n"
        f"🔗 {link}\n"
        f"👁 Показов: {current}/{total}\n"
        f"📊 Статус: {status}\n"
        f"📅 Создано: {created[:10]}\n"
    )
    await message.answer(text)


@dp.message(Command("ad_pause"))
async def cmd_ad_pause(message: Message):
    if message.from_user.id != OWNER_ID:
        return
    args = message.text.split()
    if len(args) != 2:
        await message.answer("Использование: <code>/ad_pause ID</code>")
        return
    try:
        ad_id = int(args[1])
    except ValueError:
        return
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE ads SET status = 'paused' WHERE id = ?", (ad_id,))
    conn.commit()
    conn.close()
    await message.answer(f"⏸ Реклама #{ad_id} на паузе")


@dp.message(Command("ad_resume"))
async def cmd_ad_resume(message: Message):
    if message.from_user.id != OWNER_ID:
        return
    args = message.text.split()
    if len(args) != 2:
        await message.answer("Использование: <code>/ad_resume ID</code>")
        return
    try:
        ad_id = int(args[1])
    except ValueError:
        return
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE ads SET status = 'active' WHERE id = ?", (ad_id,))
    conn.commit()
    conn.close()
    await message.answer(f"▶️ Реклама #{ad_id} активна")


@dp.message(Command("ad_delete"))
async def cmd_ad_delete(message: Message):
    if message.from_user.id != OWNER_ID:
        return
    args = message.text.split()
    if len(args) != 2:
        await message.answer("Использование: <code>/ad_delete ID</code>")
        return
    try:
        ad_id = int(args[1])
    except ValueError:
        return
    delete_ad(ad_id)
    await message.answer(f"✅ Реклама #{ad_id} удалена")


@dp.message(Command("ad_stats"))
async def cmd_ad_stats(message: Message):
    if message.from_user.id != OWNER_ID:
        return
    rows = list_ads()
    active = sum(1 for r in rows if r[9] == "active")
    finished = sum(1 for r in rows if r[9] == "finished")
    total_views = sum(r[6] for r in rows)
    text = (
        f"📊 <b>Статистика рекламы</b>\n\n"
        f"🟢 Активных: {active}\n"
        f"✅ Завершённых: {finished}\n"
        f"👁 Всего показов: {total_views}\n"
    )
    await message.answer(text)


# ============ ЗАПУСК ============
async def main():
    print("=" * 60)
    print("🚀 logiMind БОСС-ВЕРСИЯ 2.0 запускается...")
    print("🎯 AI + Premium + Стрик-награды + Рефералка + Режимы AI + Промокоды + Реклама")
    print("=" * 60)
    init_db()
    logger.info("Бот стартовал")
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        raise


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⛔ Бот остановлен")
