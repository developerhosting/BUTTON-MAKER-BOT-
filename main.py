# ============================================================
# POST BUTTON MAKER BOT
# Render Web Service + Telegram Bot
# ============================================================

import os
import telebot
from telebot import types
import sqlite3
import json
import time
import logging
import random
from datetime import datetime
from threading import Thread
from flask import Flask


# ============================================================
# CONFIG
# ============================================================

BOT_TOKEN = os.environ.get("BOT_TOKEN")

DEVELOPER_URL = "https://t.me/animefreeking"

ADMIN_IDS = [8546199829]

if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN environment variable is not set!"
    )

bot = telebot.TeleBot(
    BOT_TOKEN,
    parse_mode="HTML"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)


# ============================================================
# DATABASE
# ============================================================

db = sqlite3.connect(
    "post_button_maker.db",
    check_same_thread=False
)

cursor = db.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS layouts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    buttons TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS final_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    post_number INTEGER NOT NULL,
    message_type TEXT NOT NULL,
    file_id TEXT,
    caption TEXT DEFAULT '',
    buttons TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, post_number)
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS bot_channels (
    chat_id INTEGER PRIMARY KEY,
    title TEXT,
    added_by INTEGER,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

db.commit()


# ============================================================
# DATABASE FUNCTIONS
# ============================================================

def register_user(
    user_id,
    username,
    first_name,
    last_name=""
):
    try:
        cursor.execute(
            """
            INSERT OR REPLACE INTO users
            (
                user_id,
                username,
                first_name,
                last_name,
                last_active
            )
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                user_id,
                username,
                first_name,
                last_name
            )
        )

        db.commit()

    except Exception as e:
        logging.error(
            f"Error registering user: {e}"
        )


def log_action(user_id, action):
    try:
        cursor.execute(
            """
            INSERT INTO stats
            (user_id, action)
            VALUES (?, ?)
            """,
            (
                user_id,
                action
            )
        )

        db.commit()

    except Exception as e:
        logging.error(
            f"Error logging action: {e}"
        )


def get_total_users():
    cursor.execute(
        "SELECT COUNT(*) FROM users"
    )
    return cursor.fetchone()[0]


def get_total_layouts():
    cursor.execute(
        "SELECT COUNT(*) FROM layouts"
    )
    return cursor.fetchone()[0]


def get_total_actions():
    cursor.execute(
        "SELECT COUNT(*) FROM stats"
    )
    return cursor.fetchone()[0]


def get_today_actions():
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM stats
        WHERE DATE(timestamp) = DATE('now')
        """
    )
    return cursor.fetchone()[0]


def get_today_users():
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM users
        WHERE DATE(joined_at) = DATE('now')
        """
    )
    return cursor.fetchone()[0]


def is_admin(user_id):
    return user_id in ADMIN_IDS


# ============================================================
# FINAL POST DATABASE FUNCTIONS
# ============================================================

def get_next_post_number(user_id):

    cursor.execute(
        """
        SELECT MAX(post_number)
        FROM final_posts
        WHERE user_id = ?
        """,
        (user_id,)
    )

    row = cursor.fetchone()

    if not row or row[0] is None:
        return 1

    return row[0] + 1


def save_final_post(
    user_id,
    message_type,
    file_id,
    caption,
    buttons
):
    try:

        post_number = get_next_post_number(
            user_id
        )

        cursor.execute(
            """
            INSERT INTO final_posts
            (
                user_id,
                post_number,
                message_type,
                file_id,
                caption,
                buttons
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                post_number,
                message_type,
                file_id,
                caption or "",
                json.dumps(
                    buttons,
                    ensure_ascii=False
                )
            )
        )

        db.commit()

        return post_number

    except Exception as e:

        logging.error(
            f"Error saving final post: {e}"
        )

        return None


def get_final_post(
    user_id,
    post_number
):
    try:

        cursor.execute(
            """
            SELECT
                post_number,
                message_type,
                file_id,
                caption,
                buttons
            FROM final_posts
            WHERE user_id = ?
            AND post_number = ?
            LIMIT 1
            """,
            (
                user_id,
                post_number
            )
        )

        row = cursor.fetchone()

        if not row:
            return None

        return {
            "post_number": row[0],
            "message_type": row[1],
            "file_id": row[2],
            "caption": row[3] or "",
            "buttons": json.loads(row[4])
        }

    except Exception as e:

        logging.error(
            f"Error getting final post: {e}"
        )

        return None


# ============================================================
# BOT-ADMIN CHANNEL FUNCTIONS
# ============================================================

def upsert_bot_channel(
    chat_id,
    title,
    added_by
):
    try:

        cursor.execute(
            """
            INSERT INTO bot_channels
            (chat_id, title, added_by, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(chat_id) DO UPDATE SET
                title = excluded.title,
                added_by = excluded.added_by,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                chat_id,
                title,
                added_by
            )
        )

        db.commit()

    except Exception as e:

        logging.error(
            f"Error saving bot channel: {e}"
        )


def remove_bot_channel(chat_id):

    try:

        cursor.execute(
            "DELETE FROM bot_channels WHERE chat_id = ?",
            (chat_id,)
        )

        db.commit()

    except Exception as e:

        logging.error(
            f"Error removing bot channel: {e}"
        )


def get_user_channels(user_id):

    try:

        cursor.execute(
            """
            SELECT chat_id, title
            FROM bot_channels
            WHERE added_by = ?
            ORDER BY title
            """,
            (user_id,)
        )

        return cursor.fetchall()

    except Exception as e:

        logging.error(
            f"Error listing bot channels: {e}"
        )

        return []


# ============================================================
# SESSIONS
# ============================================================

sessions = {}


def get_session(user_id):

    if user_id not in sessions:

        sessions[user_id] = {
            "state": "idle",
            "chat_id": None,
            "source_message_id": None,
            "source_file_id": None,
            "post_message_id": None,
            "final_post_message_id": None,
            "welcome_message_id": None,
            "message_type": None,
            "caption": "",
            "buttons": [],
            "temp_text": "",
            "temp_url": "",
            "all_message_ids": [],
            "protected_message_ids": []
        }

    return sessions[user_id]


def reset_session(user_id):

    old_session = get_session(user_id)

    welcome_id = old_session.get(
        "welcome_message_id"
    )

    final_id = old_session.get(
        "final_post_message_id"
    )

    sessions[user_id] = {

        "state": "idle",

        "chat_id": None,

        "source_message_id": None,

        "source_file_id": None,

        "post_message_id": None,

        "final_post_message_id": final_id,

        "welcome_message_id": welcome_id,

        "message_type": None,

        "caption": "",

        "buttons": [],

        "temp_text": "",

        "temp_url": "",

        "all_message_ids": [],

        "protected_message_ids": []
    }

    return sessions[user_id]


# ============================================================
# MESSAGE DELETE SYSTEM
# ============================================================

def add_message_to_delete(
    user_id,
    message_id
):

    session = get_session(user_id)

    if message_id == session.get(
        "welcome_message_id"
    ):
        return

    if message_id == session.get(
        "final_post_message_id"
    ):
        return

    if message_id not in session[
        "all_message_ids"
    ]:

        session[
            "all_message_ids"
        ].append(message_id)


def add_protected_message(
    user_id,
    message_id
):

    session = get_session(user_id)

    if message_id == session.get(
        "welcome_message_id"
    ):
        return

    if message_id == session.get(
        "final_post_message_id"
    ):
        return

    if message_id not in session[
        "protected_message_ids"
    ]:

        session[
            "protected_message_ids"
        ].append(message_id)


def delete_all_messages(
    user_id,
    chat_id
):

    session = get_session(user_id)

    for msg_id in session.get(
        "all_message_ids",
        []
    ):

        try:

            if msg_id == session.get(
                "welcome_message_id"
            ):
                continue

            if msg_id == session.get(
                "final_post_message_id"
            ):
                continue

            if msg_id in session.get(
                "protected_message_ids",
                []
            ):
                continue

            bot.delete_message(
                chat_id,
                msg_id
            )

        except Exception:
            pass

    session[
        "all_message_ids"
    ] = []


def delete_protected_messages(
    user_id,
    chat_id
):

    session = get_session(user_id)

    for msg_id in session.get(
        "protected_message_ids",
        []
    ):

        try:

            if msg_id == session.get(
                "welcome_message_id"
            ):
                continue

            if msg_id == session.get(
                "final_post_message_id"
            ):
                continue

            bot.delete_message(
                chat_id,
                msg_id
            )

        except Exception:
            pass

    session[
        "protected_message_ids"
    ] = []

    session[
        "post_message_id"
    ] = None


def delete_user_message(message):

    try:

        bot.delete_message(
            message.chat.id,
            message.message_id
        )

    except Exception:
        pass


def send_step(
    chat_id,
    user_id,
    text,
    reply_markup=None
):

    delete_all_messages(
        user_id,
        chat_id
    )

    sent = bot.send_message(
        chat_id,
        text,
        reply_markup=reply_markup
    )

    add_message_to_delete(
        user_id,
        sent.message_id
    )

    return sent


# ============================================================
# WELCOME KEYBOARD
# ============================================================

def welcome_keyboard():

    keyboard = types.InlineKeyboardMarkup(
        row_width=2
    )

    keyboard.row(
        types.InlineKeyboardButton(
            "🔗 Make URL Button",
            callback_data="make_url_start"
        )
    )

    keyboard.row(
        types.InlineKeyboardButton(
            "📢 Add Channel",
            callback_data="add_channel_start"
        )
    )

    keyboard.row(
        types.InlineKeyboardButton(
            "ℹ️ Help",
            callback_data="help"
        ),
        types.InlineKeyboardButton(
            "📋 About",
            callback_data="about"
        )
    )

    keyboard.row(
        types.InlineKeyboardButton(
            "👨‍💻 Developer",
            url=DEVELOPER_URL
        )
    )

    return keyboard


# ============================================================
# START
# ============================================================

@bot.message_handler(
    commands=["start"]
)
def start(message):

    try:

        user_id = message.from_user.id

        username = (
            message.from_user.username
            or ""
        )

        first_name = (
            message.from_user.first_name
            or ""
        )

        last_name = (
            message.from_user.last_name
            or ""
        )

        register_user(
            user_id,
            username,
            first_name,
            last_name
        )

        log_action(
            user_id,
            "start"
        )

        reset_session(user_id)

        name = (
            message.from_user.first_name
            or "User"
        )

        welcome_styles = [

            (
                "╭────────────────────────╮",
                "│   👋 Hi, {name}",
                "╰────────────────────────╯"
            ),

            (
                "┏━━━━━━━━━━━━━━━━━━━━━━━━┓",
                "┃   👋 Hi, {name}",
                "┗━━━━━━━━━━━━━━━━━━━━━━━━┛"
            ),

            (
                "╔════════════════════════╗",
                "║   👋 Hi, {name}",
                "╚════════════════════════╝"
            ),

            (
                "┌────────────────────────┐",
                "│   👋 Hi, {name}",
                "└────────────────────────┘"
            ),

            (
                "⭐ ───────────────────── ⭐",
                "✨   👋 Hi, {name}",
                "⭐ ───────────────────── ⭐"
            ),

            (
                "🚀 ─────────────────── 🚀",
                "   👋 Hi, {name}",
                "🚀 ─────────────────── 🚀"
            )
        ]

        top, middle, bottom = random.choice(
            welcome_styles
        )

        text = f"""
<b>{top}
{middle.format(name=name)}
{bottom}</b>

<b>✨ POST BUTTON MAKER</b>

<b>Create. Customize. Share.</b>

Build clean, professional Telegram posts with custom URL buttons.

<b>HOW IT WORKS</b>
① Create your post
② Add your buttons
③ Customize if needed
④ Finish
⑤ Share with Telegram's native Forward / Share flow

<b>INLINE MODE</b>
Use the bot inline with your post number.

Example:
<code>@{bot.get_me().username} 1</code>

💡 Type /help for more info
"""

        WELCOME_IMAGE_URLS = [
            "https://i.ibb.co/hJtxbHzk/IMG-20260820-122329-775.jpg",
            "https://i.ibb.co/cKfmrG32/IMG-20260927-091223-106.jpg",
            "https://i.ibb.co/FLcVhfJv/IMG-20260927-091235-248.jpg",
            "https://i.ibb.co/9xK1tg1/IMG-20260825-135255-255.jpg",
            "https://i.ibb.co/qMDxF0T6/IMG-20260824-013701-793.jpg",
            "https://i.ibb.co/nq4VvDwK/IMG-20260824-013658-015.jpg",
            "https://i.ibb.co/RTjfs1TW/IMG-20260815-222219-196.jpg",
        ]

        WELCOME_IMAGE_URL = random.choice(
            WELCOME_IMAGE_URLS
        )

        try:

            sent = bot.send_photo(
                message.chat.id,
                WELCOME_IMAGE_URL,
                caption=text,
                reply_markup=welcome_keyboard()
            )

        except Exception:

            sent = bot.send_message(
                message.chat.id,
                text,
                reply_markup=welcome_keyboard()
            )

        session = get_session(user_id)

        session[
            "welcome_message_id"
        ] = sent.message_id

    except Exception as e:

        logging.error(
            f"Error in start: {e}"
        )

        bot.send_message(
            message.chat.id,
            "❌ Error starting bot."
        )


# ============================================================
# HELP
# ============================================================

@bot.message_handler(
    commands=["help"]
)
def help_command(message):

    user_id = message.from_user.id

    delete_user_message(message)

    log_action(
        user_id,
        "help"
    )

    help_text = f"""
<b>📖 HELP - POST BUTTON MAKER</b>

<b>🔹 HOW TO USE</b>

1. Click <b>Make URL Button</b>
2. Send or forward your post
3. Click <b>Add Button</b>
4. Enter button text
5. Enter URL
6. Click <b>Done</b>

<b>🔹 INLINE MODE</b>

After creating a final post:

<code>@{bot.get_me().username} 1</code>

Use the number of the post you created.

Each user has separate post numbers.

If the requested number does not exist,
no inline result will be shown.
"""

    bot.send_message(
        message.chat.id,
        help_text
    )


# ============================================================
# ABOUT
# ============================================================

@bot.message_handler(
    commands=["about"]
)
def about_command(message):

    user_id = message.from_user.id

    delete_user_message(message)

    log_action(
        user_id,
        "about"
    )

    about_text = f"""
<b>📋 ABOUT - POST BUTTON MAKER</b>

<b>🤖 BOT INFO</b>

<b>Name:</b> Post Button Maker
<b>Version:</b> 3.0

<b>Developer:</b> @animefreeking

<b>✨ FEATURES</b>

• Custom URL buttons
• All major Telegram media types
• Saved layouts
• Inline post search
• Per-user post numbering

<b>📊 STATISTICS</b>

Total Users:
<b>{get_total_users()}</b>

Total Layouts:
<b>{get_total_layouts()}</b>

<b>INLINE</b>

<code>@{bot.get_me().username} 1</code>
"""

    bot.send_message(
        message.chat.id,
        about_text
    )


# ============================================================
# HELP CALLBACK
# ============================================================

@bot.callback_query_handler(
    func=lambda call:
    call.data == "help"
)
def help_callback(call):

    bot.answer_callback_query(
        call.id
    )

    user_id = call.from_user.id
    chat_id = call.message.chat.id

    try:

        bot.delete_message(
            chat_id,
            call.message.message_id
        )

    except Exception:
        pass

    log_action(
        user_id,
        "help_callback"
    )

    help_text = f"""
<b>📖 HELP</b>

<b>HOW TO USE</b>

1. Click <b>Make URL Button</b>
2. Send your post
3. Add buttons
4. Click <b>Done</b>

<b>INLINE MODE</b>

After creating Post #1:

<code>@{bot.get_me().username} 1</code>

Post #2:

<code>@{bot.get_me().username} 2</code>

Only your own posts are returned.
"""

    keyboard = types.InlineKeyboardMarkup()

    keyboard.row(
        types.InlineKeyboardButton(
            "🔙 Back",
            callback_data="back_welcome"
        )
    )

    sent = bot.send_message(
        chat_id,
        help_text,
        reply_markup=keyboard
    )

    session = get_session(user_id)

    add_message_to_delete(
        user_id,
        sent.message_id
    )


# ============================================================
# ABOUT CALLBACK
# ============================================================

@bot.callback_query_handler(
    func=lambda call:
    call.data == "about"
)
def about_callback(call):

    bot.answer_callback_query(
        call.id
    )

    user_id = call.from_user.id
    chat_id = call.message.chat.id

    try:

        bot.delete_message(
            chat_id,
            call.message.message_id
        )

    except Exception:
        pass

    log_action(
        user_id,
        "about_callback"
    )

    about_text = f"""
<b>📋 ABOUT</b>

<b>🤖 Post Button Maker</b>

<b>Version:</b> 3.0

<b>Features</b>

• URL Buttons
• Media Posts
• Saved Layouts
• Inline Mode
• Per-user Post IDs

<b>Bot</b>

@{bot.get_me().username}
"""

    keyboard = types.InlineKeyboardMarkup()

    keyboard.row(
        types.InlineKeyboardButton(
            "🔙 Back",
            callback_data="back_welcome"
        )
    )

    sent = bot.send_message(
        chat_id,
        about_text,
        reply_markup=keyboard
    )

    add_message_to_delete(
        user_id,
        sent.message_id
    )


# ============================================================
# BACK TO WELCOME
# ============================================================

@bot.callback_query_handler(
    func=lambda call:
    call.data == "back_welcome"
)
def back_welcome(call):

    bot.answer_callback_query(
        call.id
    )

    user_id = call.from_user.id
    chat_id = call.message.chat.id

    try:

        bot.delete_message(
            chat_id,
            call.message.message_id
        )

    except Exception:
        pass

    session = get_session(user_id)

    welcome_id = session.get(
        "welcome_message_id"
    )

    if welcome_id:

        try:

            bot.edit_message_reply_markup(
                chat_id=chat_id,
                message_id=welcome_id,
                reply_markup=welcome_keyboard()
            )

            bot.edit_message_caption(
                chat_id=chat_id,
                message_id=welcome_id,
                caption=bot_caption_fallback(
                    welcome_id
                ),
                reply_markup=welcome_keyboard()
            )

        except Exception:

            try:

                bot.edit_message_reply_markup(
                    chat_id=chat_id,
                    message_id=welcome_id,
                    reply_markup=welcome_keyboard()
                )

            except Exception:
                pass

    else:

        start(
            call.message
        )


# ============================================================
# SAFE WELCOME CAPTION HELPER
# ============================================================

def bot_caption_fallback(message_id):
    return None


# ============================================================
# ADMIN TOTAL
# ============================================================

@bot.message_handler(
    commands=["total"]
)
def total_users_command(message):

    user_id = message.from_user.id

    if not is_admin(user_id):

        bot.send_message(
            message.chat.id,
            "❌ You are not authorized."
        )

        return

    delete_user_message(message)

    log_action(
        user_id,
        "admin_total"
    )

    stats_text = f"""
<b>📊 TOTAL STATISTICS</b>

<b>👥 USERS</b>

Total Users:
<b>{get_total_users()}</b>

New Today:
<b>{get_today_users()}</b>

<b>📁 LAYOUTS</b>

Total:
<b>{get_total_layouts()}</b>

<b>⚡ ACTIVITY</b>

Total:
<b>{get_total_actions()}</b>

Today:
<b>{get_today_actions()}</b>
"""

    bot.send_message(
        message.chat.id,
        stats_text
    )


# ============================================================
# ADMIN STATS
# ============================================================

@bot.message_handler(
    commands=["stats"]
)
def stats_command(message):

    user_id = message.from_user.id

    if not is_admin(user_id):

        bot.send_message(
            message.chat.id,
            "❌ You are not authorized."
        )

        return

    delete_user_message(message)

    log_action(
        user_id,
        "admin_stats"
    )

    cursor.execute(
        """
        SELECT action, COUNT(*) AS count
        FROM stats
        GROUP BY action
        ORDER BY count DESC
        """
    )

    action_stats = cursor.fetchall()

    stats_text = """
<b>📊 DETAILED STATISTICS</b>

<b>⚡ ACTION BREAKDOWN</b>
"""

    for action, count in action_stats:

        stats_text += (
            f"• {action}: "
            f"<b>{count}</b>\n"
        )

    stats_text += (
        f"\n<b>📊 TOTALS</b>"
        f"\nUsers: <b>{get_total_users()}</b>"
        f"\nLayouts: <b>{get_total_layouts()}</b>"
        f"\nActions: <b>{get_total_actions()}</b>"
    )

    bot.send_message(
        message.chat.id,
        stats_text
    )


# ============================================================
# MAKE URL START
# ============================================================

@bot.callback_query_handler(
    func=lambda call:
    call.data == "make_url_start"
)
def make_url_start(call):

    try:

        bot.answer_callback_query(
            call.id
        )

        user_id = call.from_user.id
        chat_id = call.message.chat.id

        log_action(
            user_id,
            "make_url_start"
        )

        try:

            bot.delete_message(
                chat_id,
                call.message.message_id
            )

        except Exception:
            pass

        session = reset_session(
            user_id
        )

        session["state"] = (
            "waiting_post"
        )

        session["chat_id"] = chat_id

        send_step(
            chat_id,
            user_id,
            """
<b>🔗 CREATE YOUR POST</b>

Send or forward the post you want to customize.

<b>SUPPORTED CONTENT</b>

• 🖼 Photo
• 🎬 Video
• 🎵 Audio
• 📄 Document
• 🎞 Animation
• 💬 Text

<i>Step 1 of 3</i>
""",
            reply_markup=back_to_welcome_keyboard()
        )

    except Exception as e:

        logging.error(
            f"Error in make_url_start: {e}"
        )


# ============================================================
# BACK BUTTON
# ============================================================

def back_to_welcome_keyboard():

    keyboard = types.InlineKeyboardMarkup()

    keyboard.row(
        types.InlineKeyboardButton(
            "🔙 Back",
            callback_data="back_welcome"
        )
    )

    return keyboard


# ============================================================
# MEDIA HANDLERS
# ============================================================

@bot.message_handler(
    content_types=["photo"]
)
def handle_photo(message):

    user_id = message.from_user.id

    session = get_session(
        user_id
    )

    register_user(
        user_id,
        message.from_user.username or "",
        message.from_user.first_name or "",
        message.from_user.last_name or ""
    )

    delete_user_message(message)

    if session.get("state") == "waiting_post":

        session[
            "source_file_id"
        ] = message.photo[-1].file_id

        receive_post(
            message,
            "photo"
        )

    elif session.get("state") in [
        "button_text",
        "button_url",
        "layout_name"
    ]:

        receive_text(message)

    else:

        msg = bot.send_message(
            message.chat.id,
            "❌ Please click Make URL Button first."
        )

        add_message_to_delete(
            user_id,
            msg.message_id
        )


@bot.message_handler(
    content_types=["video"]
)
def handle_video(message):

    user_id = message.from_user.id

    session = get_session(
        user_id
    )

    register_user(
        user_id,
        message.from_user.username or "",
        message.from_user.first_name or "",
        message.from_user.last_name or ""
    )

    delete_user_message(message)

    if session.get("state") == "waiting_post":

        session[
            "source_file_id"
        ] = message.video.file_id

        receive_post(
            message,
            "video"
        )

    elif session.get("state") in [
        "button_text",
        "button_url",
        "layout_name"
    ]:

        receive_text(message)

    else:

        msg = bot.send_message(
            message.chat.id,
            "❌ Please click Make URL Button first."
        )

        add_message_to_delete(
            user_id,
            msg.message_id
        )


@bot.message_handler(
    content_types=["audio"]
)
def handle_audio(message):

    user_id = message.from_user.id

    session = get_session(
        user_id
    )

    register_user(
        user_id,
        message.from_user.username or "",
        message.from_user.first_name or "",
        message.from_user.last_name or ""
    )

    delete_user_message(message)

    if session.get("state") == "waiting_post":

        session[
            "source_file_id"
        ] = message.audio.file_id

        receive_post(
            message,
            "audio"
        )

    elif session.get("state") in [
        "button_text",
        "button_url",
        "layout_name"
    ]:

        receive_text(message)

    else:

        msg = bot.send_message(
            message.chat.id,
            "❌ Please click Make URL Button first."
        )

        add_message_to_delete(
            user_id,
            msg.message_id
        )


@bot.message_handler(
    content_types=["document"]
)
def handle_document(message):

    user_id = message.from_user.id

    session = get_session(
        user_id
    )

    register_user(
        user_id,
        message.from_user.username or "",
        message.from_user.first_name or "",
        message.from_user.last_name or ""
    )

    delete_user_message(message)

    if session.get("state") == "waiting_post":

        session[
            "source_file_id"
        ] = message.document.file_id

        receive_post(
            message,
            "document"
        )

    elif session.get("state") in [
        "button_text",
        "button_url",
        "layout_name"
    ]:

        receive_text(message)

    else:

        msg = bot.send_message(
            message.chat.id,
            "❌ Please click Make URL Button first."
        )

        add_message_to_delete(
            user_id,
            msg.message_id
        )


@bot.message_handler(
    content_types=["animation"]
)
def handle_animation(message):

    user_id = message.from_user.id

    session = get_session(
        user_id
    )

    register_user(
        user_id,
        message.from_user.username or "",
        message.from_user.first_name or "",
        message.from_user.last_name or ""
    )

    delete_user_message(message)

    if session.get("state") == "waiting_post":

        session[
            "source_file_id"
        ] = message.animation.file_id

        receive_post(
            message,
            "animation"
        )

    elif session.get("state") in [
        "button_text",
        "button_url",
        "layout_name"
    ]:

        receive_text(message)

    else:

        msg = bot.send_message(
            message.chat.id,
            "❌ Please click Make URL Button first."
        )

        add_message_to_delete(
            user_id,
            msg.message_id
        )


# ============================================================
# TEXT HANDLER
# ============================================================

@bot.message_handler(
    content_types=["text"]
)
def handle_text(message):

    user_id = message.from_user.id

    session = get_session(
        user_id
    )

    state = session.get(
        "state"
    )

    if message.text.startswith("/"):
        return

    register_user(
        user_id,
        message.from_user.username or "",
        message.from_user.first_name or "",
        message.from_user.last_name or ""
    )

    delete_user_message(message)

    if state == "waiting_post":

        receive_post(
            message,
            "text"
        )

        return

    if state == "button_text":

        session[
            "temp_text"
        ] = message.text.strip()

        session[
            "state"
        ] = "button_url"

        send_step(
            message.chat.id,
            user_id,
            """
<b>🔗 BUTTON LINK</b>

Send the URL for this button.

Example:

<code>https://example.com</code>

<i>Step 3 of 3</i>
"""
        )

        return

    if state == "button_url":

        url = message.text.strip()

        if not (
            url.startswith("https://")
            or
            url.startswith("http://")
        ):

            send_step(
                message.chat.id,
                user_id,
                """
<b>❌ INVALID URL</b>

Must start with:

<code>https://</code>

or

<code>http://</code>

Try again.
"""
            )

            return

        session[
            "temp_url"
        ] = url

        session[
            "state"
        ] = "button_color"

        send_step(
            message.chat.id,
            user_id,
            """
<b>🎨 BUTTON COLOUR</b>

Pick a colour for this button.

<i>(Telegram only allows 3 real button colours: Blue, Green or Red — plus Default. Requires a recent Telegram app version.)</i>
""",
            color_picker_keyboard()
        )

        return

    if state == "layout_name":

        layout_name_handler(
            message
        )

        return

    if state == "adding_channel":

        handle_add_channel(
            message
        )

        return


# ============================================================
# RECEIVE POST
# ============================================================

def receive_post(
    message,
    media_type
):

    user_id = message.from_user.id

    old_session = get_session(
        user_id
    )

    welcome_id = old_session.get(
        "welcome_message_id"
    )

    session = reset_session(
        user_id
    )

    session[
        "welcome_message_id"
    ] = welcome_id

    session[
        "state"
    ] = "editing"

    session[
        "message_type"
    ] = media_type

    session[
        "source_message_id"
    ] = message.message_id

    session[
        "chat_id"
    ] = message.chat.id

    if media_type == "text":

        session[
            "caption"
        ] = (
            getattr(message, "html_text", None)
            or message.text
            or ""
        )

    else:

        session[
            "caption"
        ] = (
            getattr(message, "html_caption", None)
            or message.caption
            or ""
        )

    if (
        media_type != "text"
        and
        not session.get(
            "source_file_id"
        )
    ):

        if media_type == "photo":

            session[
                "source_file_id"
            ] = message.photo[-1].file_id

        elif media_type == "video":

            session[
                "source_file_id"
            ] = message.video.file_id

        elif media_type == "audio":

            session[
                "source_file_id"
            ] = message.audio.file_id

        elif media_type == "document":

            session[
                "source_file_id"
            ] = message.document.file_id

        elif media_type == "animation":

            session[
                "source_file_id"
            ] = message.animation.file_id

    log_action(
        user_id,
        f"post_{media_type}"
    )

    send_editor_post(
        message.chat.id,
        user_id
    )


# ============================================================
# SEND EDITOR POST
# ============================================================

def send_editor_post(
    chat_id,
    user_id
):

    session = get_session(
        user_id
    )

    delete_all_messages(
        user_id,
        chat_id
    )

    message_type = session.get(
        "message_type"
    )

    caption = session.get(
        "caption",
        ""
    )

    keyboard = types.InlineKeyboardMarkup()

    keyboard.row(
        types.InlineKeyboardButton(
            "➕ Add Button",
            callback_data="add_button"
        )
    )

    if session["buttons"]:

        keyboard.row(
            types.InlineKeyboardButton(
                "✅ Done",
                callback_data="finish"
            ),
            types.InlineKeyboardButton(
                "🔄 Clear",
                callback_data="clear_buttons"
            )
        )

        keyboard.row(
            types.InlineKeyboardButton(
                "💾 Save Layout",
                callback_data="save_layout"
            ),
            types.InlineKeyboardButton(
                "📁 Saved",
                callback_data="saved"
            )
        )

    file_id = session.get(
        "source_file_id"
    )

    try:

        if (
            message_type == "photo"
            and file_id
        ):

            post = bot.send_photo(
                chat_id,
                file_id,
                caption=caption,
                reply_markup=keyboard
            )

        elif (
            message_type == "video"
            and file_id
        ):

            post = bot.send_video(
                chat_id,
                file_id,
                caption=caption,
                reply_markup=keyboard
            )

        elif (
            message_type == "audio"
            and file_id
        ):

            post = bot.send_audio(
                chat_id,
                file_id,
                caption=caption,
                reply_markup=keyboard
            )

        elif (
            message_type == "document"
            and file_id
        ):

            post = bot.send_document(
                chat_id,
                file_id,
                caption=caption,
                reply_markup=keyboard
            )

        elif (
            message_type == "animation"
            and file_id
        ):

            post = bot.send_animation(
                chat_id,
                file_id,
                caption=caption,
                reply_markup=keyboard
            )

        elif message_type == "text":

            post = bot.send_message(
                chat_id,
                caption,
                reply_markup=keyboard
            )

        else:

            bot.send_message(
                chat_id,
                "❌ Unsupported media type."
            )

            return

        session[
            "post_message_id"
        ] = post.message_id

        add_protected_message(
            user_id,
            post.message_id
        )

    except Exception as e:

        logging.error(
            f"Error sending editor post: {e}"
        )

        msg = bot.send_message(
            chat_id,
            "❌ Error processing your post."
        )

        add_message_to_delete(
            user_id,
            msg.message_id
        )


# ============================================================
# COLOURED BUTTON
# ============================================================

class ColoredButton(types.InlineKeyboardButton):

    def __init__(
        self,
        text,
        url=None,
        style=None,
        **kwargs
    ):

        super().__init__(
            text=text,
            url=url,
            **kwargs
        )

        self.style = style

    def to_dict(self):

        data = super().to_dict()

        if self.style:
            data["style"] = self.style

        return data


BUTTON_STYLES = [
    ("🔵 Blue", "primary"),
    ("🟢 Green", "success"),
    ("🔴 Red", "danger"),
    ("⚪ Default", None),
]


def build_url_keyboard(buttons):

    keyboard = types.InlineKeyboardMarkup()

    for button in buttons:

        keyboard.row(
            ColoredButton(
                button["text"],
                url=button["url"],
                style=button.get("style")
            )
        )

    return keyboard


def color_picker_keyboard():

    keyboard = types.InlineKeyboardMarkup(
        row_width=2
    )

    for label, style in BUTTON_STYLES:

        keyboard.add(
            types.InlineKeyboardButton(
                label,
                callback_data=f"style_{style or 'none'}"
            )
        )

    return keyboard


@bot.callback_query_handler(
    func=lambda call:
    call.data.startswith("style_")
)
def button_color_chosen(call):

    bot.answer_callback_query(
        call.id
    )

    user_id = call.from_user.id
    chat_id = call.message.chat.id

    session = get_session(
        user_id
    )

    if session.get("state") != "button_color":
        return

    choice = call.data[
        len("style_"):
    ]

    style = None if choice == "none" else choice

    text = session.get(
        "temp_text",
        ""
    )

    url = session.get(
        "temp_url",
        ""
    )

    session[
        "buttons"
    ].append(
        {
            "text": text,
            "url": url,
            "style": style
        }
    )

    session[
        "state"
    ] = "editing"

    session[
        "temp_text"
    ] = ""

    session[
        "temp_url"
    ] = ""

    log_action(
        user_id,
        f"button_style_{choice}"
    )

    send_editor_post(
        chat_id,
        user_id
    )


# ============================================================
# ADD BUTTON
# ============================================================

@bot.callback_query_handler(
    func=lambda call:
    call.data == "add_button"
)
def add_button(call):

    bot.answer_callback_query(
        call.id
    )

    user_id = call.from_user.id
    chat_id = call.message.chat.id

    log_action(
        user_id,
        "add_button"
    )

    session = get_session(
        user_id
    )

    session[
        "state"
    ] = "button_text"

    send_step(
        chat_id,
        user_id,
        """
<b>🔘 BUTTON TEXT</b>

Send the text for your button.

Example:

<code>Click Here</code>
"""
    )


# ============================================================
# CLEAR BUTTONS
# ============================================================

@bot.callback_query_handler(
    func=lambda call:
    call.data == "clear_buttons"
)
def clear_buttons(call):

    bot.answer_callback_query(
        call.id
    )

    user_id = call.from_user.id
    chat_id = call.message.chat.id

    session = get_session(
        user_id
    )

    session[
        "buttons"
    ] = []

    session[
        "state"
    ] = "editing"

    log_action(
        user_id,
        "clear_buttons"
    )

    send_editor_post(
        chat_id,
        user_id
    )


# ============================================================
# FINISH
# ============================================================

@bot.callback_query_handler(
    func=lambda call:
    call.data == "finish"
)
def finish(call):

    bot.answer_callback_query(
        call.id
    )

    user_id = call.from_user.id
    chat_id = call.message.chat.id

    session = get_session(
        user_id
    )

    if not session["buttons"]:

        msg = bot.send_message(
            chat_id,
            "❌ Add at least one button first."
        )

        add_message_to_delete(
            user_id,
            msg.message_id
        )

        return

    log_action(
        user_id,
        "finish"
    )

    try:

        delete_protected_messages(
            user_id,
            chat_id
        )

        message_type = session.get(
            "message_type"
        )

        caption = session.get(
            "caption",
            ""
        )

        file_id = session.get(
            "source_file_id"
        )

        buttons = session[
            "buttons"
        ]

        keyboard = build_url_keyboard(
            buttons
        )

        if (
            message_type == "photo"
            and file_id
        ):

            final_post = bot.send_photo(
                chat_id,
                file_id,
                caption=caption,
                reply_markup=keyboard
            )

        elif (
            message_type == "video"
            and file_id
        ):

            final_post = bot.send_video(
                chat_id,
                file_id,
                caption=caption,
                reply_markup=keyboard
            )

        elif (
            message_type == "audio"
            and file_id
        ):

            final_post = bot.send_audio(
                chat_id,
                file_id,
                caption=caption,
                reply_markup=keyboard
            )

        elif (
            message_type == "document"
            and file_id
        ):

            final_post = bot.send_document(
                chat_id,
                file_id,
                caption=caption,
                reply_markup=keyboard
            )

        elif (
            message_type == "animation"
            and file_id
        ):

            final_post = bot.send_animation(
                chat_id,
                file_id,
                caption=caption,
                reply_markup=keyboard
            )

        elif message_type == "text":

            final_post = bot.send_message(
                chat_id,
                caption,
                reply_markup=keyboard
            )

        else:

            bot.send_message(
                chat_id,
                "❌ Unsupported media type."
            )

            return

        post_number = save_final_post(
            user_id=user_id,
            message_type=message_type,
            file_id=file_id,
            caption=caption,
            buttons=buttons
        )

        if post_number is None:

            raise Exception(
                "Unable to save final post."
            )

        session[
            "final_post_message_id"
        ] = final_post.message_id

        session[
            "state"
        ] = "finished"

        forward_keyboard = types.InlineKeyboardMarkup()

        forward_keyboard.row(
            types.InlineKeyboardButton(
                "↗️ Forward",
                callback_data=f"pick_channel:{post_number}"
            )
        )

        success_msg = bot.send_message(
            chat_id,
            f"""
<b>✅ POST READY!</b>

<b>Post ID:</b>
<code>{post_number}</code>

<b>Inline:</b>
<code>@{bot.get_me().username} {post_number}</code>

You can now share this post using Telegram's native share/forward feature.
""",
            reply_markup=forward_keyboard
        )

        add_message_to_delete(
            user_id,
            success_msg.message_id
        )

        welcome_id = session.get(
            "welcome_message_id"
        )

        final_id = session.get(
            "final_post_message_id"
        )

        reset_session(
            user_id
        )

        session = get_session(
            user_id
        )

        session[
            "welcome_message_id"
        ] = welcome_id

        session[
            "final_post_message_id"
        ] = final_id

        session[
            "state"
        ] = "idle"

    except Exception as error:

        logging.exception(
            f"Finish error: {error}"
        )

        msg = bot.send_message(
            chat_id,
            "❌ Unable to prepare the post."
        )

        add_message_to_delete(
            user_id,
            msg.message_id
        )


# ============================================================
# SAVE LAYOUT
# ============================================================

@bot.callback_query_handler(
    func=lambda call:
    call.data == "save_layout"
)
def save_layout(call):

    bot.answer_callback_query(
        call.id
    )

    user_id = call.from_user.id
    chat_id = call.message.chat.id

    session = get_session(
        user_id
    )

    if not session["buttons"]:

        msg = bot.send_message(
            chat_id,
            "❌ Add at least one button first."
        )

        add_message_to_delete(
            user_id,
            msg.message_id
        )

        return

    log_action(
        user_id,
        "save_layout"
    )

    session[
        "state"
    ] = "layout_name"

    send_step(
        chat_id,
        user_id,
        """
<b>💾 SAVE LAYOUT</b>

Send a name for this button layout.
"""
    )


# ============================================================
# LAYOUT NAME
# ============================================================

def layout_name_handler(message):

    user_id = message.from_user.id
    chat_id = message.chat.id

    session = get_session(
        user_id
    )

    name = message.text.strip()

    if not name:
        return

    cursor.execute(
        """
        INSERT INTO layouts
        (user_id, name, buttons)
        VALUES (?, ?, ?)
        """,
        (
            user_id,
            name,
            json.dumps(
                session["buttons"],
                ensure_ascii=False
            )
        )
    )

    db.commit()

    log_action(
        user_id,
        "layout_saved"
    )

    session[
        "state"
    ] = "editing"

    msg = bot.send_message(
        chat_id,
        f"""
✅ <b>LAYOUT SAVED</b>

Name:
<code>{name}</code>

Buttons:
<b>{len(session["buttons"])}</b>
"""
    )

    add_message_to_delete(
        user_id,
        msg.message_id
    )

    send_editor_post(
        chat_id,
        user_id
    )


# ============================================================
# SAVED
# ============================================================

@bot.callback_query_handler(
    func=lambda call:
    call.data == "saved"
)
def saved(call):

    bot.answer_callback_query(
        call.id
    )

    user_id = call.from_user.id
    chat_id = call.message.chat.id

    cursor.execute(
        """
        SELECT id, name, buttons
        FROM layouts
        WHERE user_id = ?
        ORDER BY id DESC
        """,
        (user_id,)
    )

    rows = cursor.fetchall()

    if not rows:

        msg = bot.send_message(
            chat_id,
            "📁 <b>No saved layouts found.</b>"
        )

        add_message_to_delete(
            user_id,
            msg.message_id
        )

        return

    text = "<b>📁 SAVED LAYOUTS</b>\n\n"

    keyboard = types.InlineKeyboardMarkup()

    for row in rows:

        layout_id = row[0]
        name = row[1]
        buttons = json.loads(row[2])

        text += (
            f"📌 <b>{name}</b>\n"
            f"🔗 Buttons: {len(buttons)}\n\n"
        )

        keyboard.row(
            types.InlineKeyboardButton(
                f"▶️ {name[:20]}",
                callback_data=f"use_{layout_id}"
            ),
            types.InlineKeyboardButton(
                "🗑",
                callback_data=f"delete_{layout_id}"
            )
        )

    msg = bot.send_message(
        chat_id,
        text,
        reply_markup=keyboard
    )

    add_message_to_delete(
        user_id,
        msg.message_id
    )


# ============================================================
# USE SAVED
# ============================================================

@bot.callback_query_handler(
    func=lambda call:
    call.data.startswith("use_")
)
def use_saved(call):

    bot.answer_callback_query(
        call.id
    )

    user_id = call.from_user.id
    chat_id = call.message.chat.id

    layout_id = int(
        call.data.replace(
            "use_",
            ""
        )
    )

    cursor.execute(
        """
        SELECT buttons
        FROM layouts
        WHERE id = ?
        AND user_id = ?
        """,
        (
            layout_id,
            user_id
        )
    )

    row = cursor.fetchone()

    try:

        bot.delete_message(
            chat_id,
            call.message.message_id
        )

    except Exception:
        pass

    if not row:

        msg = bot.send_message(
            chat_id,
            "❌ Layout not found."
        )

        add_message_to_delete(
            user_id,
            msg.message_id
        )

        return

    session = get_session(
        user_id
    )

    session[
        "buttons"
    ] = json.loads(
        row[0]
    )

    session[
        "state"
    ] = "editing"

    if session.get(
        "source_message_id"
    ):

        send_editor_post(
            chat_id,
            user_id
        )

    else:

        msg = bot.send_message(
            chat_id,
            "✅ Layout loaded. Please send your post first."
        )

        add_message_to_delete(
            user_id,
            msg.message_id
        )


# ============================================================
# DELETE SAVED
# ============================================================

@bot.callback_query_handler(
    func=lambda call:
    call.data.startswith("delete_")
)
def delete_saved(call):

    bot.answer_callback_query(
        call.id
    )

    user_id = call.from_user.id
    chat_id = call.message.chat.id

    layout_id = int(
        call.data.replace(
            "delete_",
            ""
        )
    )

    cursor.execute(
        """
        DELETE FROM layouts
        WHERE id = ?
        AND user_id = ?
        """,
        (
            layout_id,
            user_id
        )
    )

    db.commit()

    try:

        bot.delete_message(
            chat_id,
            call.message.message_id
        )

    except Exception:
        pass

    msg = bot.send_message(
        chat_id,
        "✅ <b>Layout deleted.</b>"
    )

    add_message_to_delete(
        user_id,
        msg.message_id
    )


# ============================================================
# INLINE MODE
# ============================================================

@bot.inline_handler(
    func=lambda query: True
)
def inline_query(query):

    user_id = query.from_user.id

    register_user(
        user_id,
        query.from_user.username or "",
        query.from_user.first_name or "",
        query.from_user.last_name or ""
    )

    query_text = (
        query.query or ""
    ).strip()

    if not query_text:

        bot.answer_inline_query(
            query.id,
            [],
            cache_time=0,
            is_personal=True
        )

        return

    if not query_text.isdigit():

        bot.answer_inline_query(
            query.id,
            [],
            cache_time=0,
            is_personal=True
        )

        return

    try:

        post_number = int(
            query_text
        )

    except ValueError:

        bot.answer_inline_query(
            query.id,
            [],
            cache_time=0,
            is_personal=True
        )

        return

    if post_number <= 0:

        bot.answer_inline_query(
            query.id,
            [],
            cache_time=0,
            is_personal=True
        )

        return

    post = get_final_post(
        user_id,
        post_number
    )

    if not post:

        bot.answer_inline_query(
            query.id,
            [],
            cache_time=0,
            is_personal=True
        )

        return

    keyboard = None

    if post["buttons"]:

        keyboard = build_url_keyboard(
            post["buttons"]
        )

    results = []

    message_type = post[
        "message_type"
    ]

    file_id = post[
        "file_id"
    ]

    caption = post[
        "caption"
    ]

    if (
        message_type == "photo"
        and file_id
    ):

        results.append(
            types.InlineQueryResultCachedPhoto(
                id=f"{user_id}_{post_number}",
                photo_file_id=file_id,
                caption=caption,
                reply_markup=keyboard
            )
        )

    elif (
        message_type == "video"
        and file_id
    ):

        results.append(
            types.InlineQueryResultCachedVideo(
                id=f"{user_id}_{post_number}",
                video_file_id=file_id,
                title=f"Post {post_number}",
                caption=caption,
                reply_markup=keyboard
            )
        )

    elif (
        message_type == "audio"
        and file_id
    ):

        results.append(
            types.InlineQueryResultCachedAudio(
                id=f"{user_id}_{post_number}",
                audio_file_id=file_id,
                caption=caption,
                reply_markup=keyboard
            )
        )

    elif (
        message_type == "document"
        and file_id
    ):

        results.append(
            types.InlineQueryResultCachedDocument(
                id=f"{user_id}_{post_number}",
                document_file_id=file_id,
                title=f"Post {post_number}",
                description=caption[:100],
                caption=caption,
                reply_markup=keyboard
            )
        )

    elif (
        message_type == "animation"
        and file_id
    ):

        results.append(
            types.InlineQueryResultCachedGif(
                id=f"{user_id}_{post_number}",
                gif_file_id=file_id,
                title=f"Post {post_number}",
                caption=caption,
                reply_markup=keyboard
            )
        )

    elif message_type == "text":

        results.append(
            types.InlineQueryResultArticle(
                id=f"{user_id}_{post_number}",
                title=f"Post {post_number}",
                description=caption[:100],
                input_message_content=
                types.InputTextMessageContent(
                    message_text=caption,
                    parse_mode="HTML"
                ),
                reply_markup=keyboard
            )
        )

    bot.answer_inline_query(
        query.id,
        results,
        cache_time=0,
        is_personal=True
    )

    log_action(
        user_id,
        f"inline_{post_number}"
    )


# ============================================================
# ADD CHANNEL
# ============================================================

@bot.callback_query_handler(
    func=lambda call:
    call.data == "add_channel_start"
)
def add_channel_start(call):

    bot.answer_callback_query(
        call.id
    )

    user_id = call.from_user.id
    chat_id = call.message.chat.id

    session = get_session(
        user_id
    )

    session[
        "state"
    ] = "adding_channel"

    session[
        "chat_id"
    ] = chat_id

    send_step(
        chat_id,
        user_id,
        """
<b>📢 ADD CHANNEL</b>

Send me the channel's <b>@username</b> or its <b>t.me link</b>.

Example:
<code>@mychannel</code>
or
<code>https://t.me/mychannel</code>

⚠️ I must already be an <b>Admin</b> in that channel — add me there first if you haven't.
"""
    )


def resolve_channel_identifier(text):

    text = text.strip()

    if (
        text.startswith("https://t.me/")
        or text.startswith("http://t.me/")
    ):

        text = text.split("t.me/")[-1]

    text = text.strip("/")

    if text.startswith("@"):
        return text

    try:
        return int(text)

    except ValueError:
        return f"@{text}"


def handle_add_channel(message):

    user_id = message.from_user.id
    chat_id = message.chat.id

    session = get_session(
        user_id
    )

    session[
        "state"
    ] = "idle"

    identifier = resolve_channel_identifier(
        message.text
    )

    try:

        chat = bot.get_chat(
            identifier
        )

    except Exception:

        bot.send_message(
            chat_id,
            """
<b>❌ Couldn't find that channel</b>

Double check the @username or link and try again from <b>Add Channel</b>.
"""
        )

        return

    if chat.type != "channel":

        bot.send_message(
            chat_id,
            "❌ That's not a channel."
        )

        return

    try:

        member = bot.get_chat_member(
            chat.id,
            bot.get_me().id
        )

    except Exception:

        bot.send_message(
            chat_id,
            "❌ I couldn't check my status there. Make sure I've been added to the channel."
        )

        return

    if member.status != "administrator":

        bot.send_message(
            chat_id,
            f"""
<b>❌ I'm not an Admin in "{chat.title}" yet</b>

Add me as <b>Admin</b> in that channel first, then try <b>Add Channel</b> again.
"""
        )

        return

    upsert_bot_channel(
        chat.id,
        chat.title or str(chat.id),
        user_id
    )

    log_action(
        user_id,
        "add_channel"
    )

    bot.send_message(
        chat_id,
        f"""
<b>✅ "{chat.title}" added!</b>

It will now show up under the <b>Forward</b> option on any post.
"""
    )


# ============================================================
# TRACK CHANNELS
# ============================================================

@bot.my_chat_member_handler()
def track_bot_admin_channels(update):

    try:

        chat = update.chat

        if chat.type != "channel":
            return

        new_status = update.new_chat_member.status

        performed_by = (
            update.from_user.id
            if update.from_user
            else None
        )

        if new_status == "administrator":

            upsert_bot_channel(
                chat.id,
                chat.title or str(chat.id),
                performed_by
            )

        else:

            remove_bot_channel(
                chat.id
            )

    except Exception as e:

        logging.error(
            f"my_chat_member handling failed: {e}"
        )


# ============================================================
# FORWARD POST TO CHANNEL
# ============================================================

@bot.callback_query_handler(
    func=lambda call:
    call.data.startswith("pick_channel:")
)
def pick_channel(call):

    bot.answer_callback_query(
        call.id
    )

    user_id = call.from_user.id
    chat_id = call.message.chat.id

    post_number = call.data.split(
        ":"
    )[1]

    channels = get_user_channels(
        user_id
    )

    if not channels:

        bot.send_message(
            chat_id,
            """
<b>❌ No admin channels found</b>

Add me as <b>Admin</b> to your channel first, then this option will show it here.
"""
        )

        return

    keyboard = types.InlineKeyboardMarkup()

    for ch_id, title in channels:

        keyboard.row(
            types.InlineKeyboardButton(
                f"📢 {title}",
                callback_data=f"sendto:{ch_id}:{post_number}"
            )
        )

    bot.send_message(
        chat_id,
        "<b>📤 Select a channel to send this post to:</b>",
        reply_markup=keyboard
    )


@bot.callback_query_handler(
    func=lambda call:
    call.data.startswith("sendto:")
)
def send_to_channel(call):

    bot.answer_callback_query(
        call.id
    )

    user_id = call.from_user.id
    chat_id = call.message.chat.id

    parts = call.data.split(":")

    target_chat_id = int(parts[1])
    post_number = int(parts[2])

    post = get_final_post(
        user_id,
        post_number
    )

    if not post:

        bot.send_message(
            chat_id,
            "❌ Couldn't find that post anymore."
        )

        return

    message_type = post["message_type"]
    caption = post["caption"]
    file_id = post["file_id"]
    buttons = post["buttons"]

    keyboard = (
        build_url_keyboard(buttons)
        if buttons
        else None
    )

    try:

        if (
            message_type == "photo"
            and file_id
        ):

            bot.send_photo(
                target_chat_id,
                file_id,
                caption=caption,
                reply_markup=keyboard
            )

        elif (
            message_type == "video"
            and file_id
        ):

            bot.send_video(
                target_chat_id,
                file_id,
                caption=caption,
                reply_markup=keyboard
            )

        elif (
            message_type == "audio"
            and file_id
        ):

            bot.send_audio(
                target_chat_id,
                file_id,
                caption=caption,
                reply_markup=keyboard
            )

        elif (
            message_type == "document"
            and file_id
        ):

            bot.send_document(
                target_chat_id,
                file_id,
                caption=caption,
                reply_markup=keyboard
            )

        elif (
            message_type == "animation"
            and file_id
        ):

            bot.send_animation(
                target_chat_id,
                file_id,
                caption=caption,
                reply_markup=keyboard
            )

        elif message_type == "text":

            bot.send_message(
                target_chat_id,
                caption,
                reply_markup=keyboard
            )

        else:

            bot.send_message(
                chat_id,
                "❌ Unsupported post type."
            )

            return

        log_action(
            user_id,
            f"forward_to_{target_chat_id}"
        )

        bot.send_message(
            chat_id,
            "✅ Sent to the channel!"
        )

    except Exception as e:

        logging.error(
            f"Forward to channel failed: {e}"
        )

        bot.send_message(
            chat_id,
            f"❌ Couldn't send it there: {e}"
        )


# ============================================================
# CANCEL
# ============================================================

@bot.message_handler(
    commands=["cancel"]
)
def cancel(message):

    user_id = message.from_user.id
    chat_id = message.chat.id

    log_action(
        user_id,
        "cancel"
    )

    delete_user_message(
        message
    )

    delete_protected_messages(
        user_id,
        chat_id
    )

    delete_all_messages(
        user_id,
        chat_id
    )

    session = get_session(
        user_id
    )

    welcome_id = session.get(
        "welcome_message_id"
    )

    final_id = session.get(
        "final_post_message_id"
    )

    reset_session(
        user_id
    )

    session = get_session(
        user_id
    )

    session[
        "welcome_message_id"
    ] = welcome_id

    session[
        "final_post_message_id"
    ] = final_id

    session[
        "state"
    ] = "idle"


# ============================================================
# POLLING
# ============================================================

def run_bot():

    print("=" * 50)
    print("POST BUTTON MAKER BOT")
    print("=" * 50)
    print("Inline Mode: ENABLED")
    print("Per-user Post IDs: ENABLED")
    print("Render Web Service: ENABLED")
    print("Status: Running...")
    print("=" * 50)

    while True:

        try:

            bot.infinity_polling(
                skip_pending=True,
                timeout=60,
                allowed_updates=[
                    "message",
                    "edited_message",
                    "channel_post",
                    "edited_channel_post",
                    "inline_query",
                    "chosen_inline_result",
                    "callback_query",
                    "my_chat_member",
                    "chat_member",
                ]
            )

        except KeyboardInterrupt:

            print(
                "\nBot stopped by user."
            )

            break

        except Exception as error:

            logging.error(
                f"Polling error: {error}"
            )

            time.sleep(5)


# ============================================================
# FLASK WEB SERVER FOR RENDER
# ============================================================

app = Flask(__name__)


@app.route("/")
def home():

    return "POST BUTTON MAKER BOT IS RUNNING"


@app.route("/health")
def health():

    return "OK"


def run_web_server():

    port = int(
        os.environ.get(
            "PORT",
            "10000"
        )
    )

    app.run(
        host="0.0.0.0",
        port=port
    )


# ============================================================
# START BOT + WEB SERVER
# ============================================================

if __name__ == "__main__":

    try:

        print(
            "✅ BOT_TOKEN found!"
        )

        print(
            "🌐 Starting Render web server..."
        )

        web_thread = Thread(
            target=run_web_server,
            daemon=True
        )

        web_thread.start()

        print(
            "🤖 Starting Telegram bot..."
        )

        run_bot()

    except Exception as e:

        print(
            f"❌ Fatal Error: {e}"
        )
