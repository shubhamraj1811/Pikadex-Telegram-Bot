import telebot
from telebot import types
from telebot.types import BotCommand
import sqlite3
import math

# Paste your token here!
TOKEN = "TOKEN"
bot = telebot.TeleBot(TOKEN)
DB_FILE = "rejuv_bot.db"

user_catch_data = {}
ITEMS_PER_PAGE = 20


# ==========================================
# DATABASE SETUP & HELPERS
# ==========================================
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS caught_pokemon (
            user_id INTEGER,
            pokemon_id INTEGER,
            name TEXT,
            UNIQUE(user_id, pokemon_id),
            UNIQUE(user_id, name)
        )
    """)
    conn.commit()
    conn.close()


def execute_query(query, params=(), fetch=False):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute(query, params)
        conn.commit()
        if fetch:
            return cursor.fetchall()
        return cursor.rowcount
    except sqlite3.IntegrityError:
        conn.close()
        return "DUPLICATE_ERROR"
    finally:
        conn.close()


# ==========================================
# MAIN MENU & BUTTONS
# ==========================================
@bot.message_handler(commands=["start", "help"])
def send_welcome(message):
    welcome_text = (
        "⚡ *PIKADEX 💛 Trainer's Companion*\n\n"
        "Welcome back Trainer!"
        "I'm Pikadex, What would you like to do?"
    )

    markup = types.InlineKeyboardMarkup()
    btn_catch = types.InlineKeyboardButton("➕ Catch", callback_data="action_catch")
    btn_release = types.InlineKeyboardButton(
        "❌ Release", callback_data="action_release"
    )
    btn_view = types.InlineKeyboardButton("📜 View Dex", callback_data="action_view")
    btn_search = types.InlineKeyboardButton("🔍 Search", callback_data="action_search")
    btn_stats = types.InlineKeyboardButton("📊 Stats", callback_data="action_stats")

    markup.row(btn_catch, btn_release)
    markup.row(btn_search, btn_view)
    markup.row(btn_stats)

    bot.reply_to(message, welcome_text, parse_mode="Markdown", reply_markup=markup)


# ==========================================
# BUTTON CLICK ROUTER
# ==========================================
@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    chat_id = call.message.chat.id
    bot.answer_callback_query(call.id)

    if call.data == "action_catch":
        msg = bot.send_message(
            chat_id,
            "Awesome! What is the **Name** of the Pokémon?",
            parse_mode="Markdown",
        )
        bot.register_next_step_handler(msg, process_name_step)

    elif call.data == "action_release":
        msg = bot.send_message(
            chat_id,
            "Enter the **Name** or **ID** to release:",
            parse_mode="Markdown",
        )
        bot.register_next_step_handler(msg, process_release_step)

    elif call.data == "action_search":
        msg = bot.send_message(
            chat_id,
            "🔍 Enter the **Name** or **ID** of the Pokémon to search:",
            parse_mode="Markdown",
        )
        bot.register_next_step_handler(msg, process_search_step)

    elif call.data == "action_view":
        handle_view(chat_id, page=0)

    elif call.data.startswith("page_view_"):
        page_number = int(call.data.split("_")[2])
        handle_view(chat_id, page=page_number, message_id=call.message.message_id)

    elif call.data == "action_home":
        bot.delete_message(chat_id, call.message.message_id)
        send_welcome(call.message)

    elif call.data == "action_stats":
        handle_stats(chat_id)


# ==========================================
# SLASH COMMAND ROUTERS
# ==========================================
@bot.message_handler(commands=["catch"])
def command_catch(message):
    msg = bot.send_message(
        message.chat.id,
        "Awesome! What is the **Name** of the Pokémon?",
        parse_mode="Markdown",
    )
    bot.register_next_step_handler(msg, process_name_step)


@bot.message_handler(commands=["search"])
def command_search(message):
    msg = bot.send_message(
        message.chat.id,
        "🔍 Enter the **Name** or **ID** of the Pokémon to search:",
        parse_mode="Markdown",
    )
    bot.register_next_step_handler(msg, process_search_step)


@bot.message_handler(commands=["release"])
def command_release(message):
    msg = bot.send_message(
        message.chat.id,
        "Enter the **Name** or **ID** to release:",
        parse_mode="Markdown",
    )
    bot.register_next_step_handler(msg, process_release_step)


@bot.message_handler(commands=["view"])
def command_view(message):
    handle_view(message.chat.id, page=0)


@bot.message_handler(commands=["stats"])
def command_stats(message):
    handle_stats(message.chat.id)


# ==========================================
# FEATURE: SEARCHING (LIGHTNING FAST)
# ==========================================
def process_search_step(message):
    if message.text.startswith("/"):
        bot.reply_to(message, "Action canceled.")
        return

    term = message.text.strip().upper()
    user_id = message.from_user.id

    if term.isdigit():
        result = execute_query(
            "SELECT pokemon_id, name FROM caught_pokemon WHERE user_id = ? AND pokemon_id = ?",
            (user_id, int(term)),
            fetch=True,
        )
    else:
        result = execute_query(
            "SELECT pokemon_id, name FROM caught_pokemon WHERE user_id = ? AND name = ?",
            (user_id, term),
            fetch=True,
        )

    if result:
        pid, name = result[0]
        caption_text = (
            f"✅ *IN POKÉDEX!*\nYou have already caught **{name}** (ID: #{pid:04d})."
        )
        bot.send_message(message.chat.id, caption_text, parse_mode="Markdown")
    else:
        bot.send_message(
            message.chat.id,
            f"❌ **{term}** is NOT in your Pokédex yet!",
            parse_mode="Markdown",
        )


# ==========================================
# FEATURE: CATCHING (LIGHTNING FAST)
# ==========================================
def process_name_step(message):
    if message.text.startswith("/"):
        bot.reply_to(message, "Action canceled.")
        return

    name = message.text.strip().upper()
    user_catch_data[message.chat.id] = {"name": name}

    msg = bot.send_message(
        message.chat.id,
        f"What is the **Pokédex ID** for {name}?",
        parse_mode="Markdown",
    )
    bot.register_next_step_handler(msg, process_id_step)


def process_id_step(message):
    if message.text.startswith("/"):
        bot.reply_to(message, "Action canceled.")
        return

    try:
        pid = int(message.text.strip())
        name = user_catch_data[message.chat.id]["name"]
        user_id = message.from_user.id

        res = execute_query(
            "INSERT INTO caught_pokemon (user_id, pokemon_id, name) VALUES (?, ?, ?)",
            (user_id, pid, name),
        )

        if res == "DUPLICATE_ERROR":
            bot.send_message(
                message.chat.id,
                f"❌ You already have **{name}** or ID **{pid}** registered!",
                parse_mode="Markdown",
            )
        else:
            caption_text = (
                f"✅ *Caught!*\nSuccessfully registered **{name}** (ID: #{pid:04d})."
            )
            bot.send_message(message.chat.id, caption_text, parse_mode="Markdown")

        del user_catch_data[message.chat.id]

    except ValueError:
        bot.send_message(
            message.chat.id,
            "⚠️ The ID must be a number! Send /start to try again.",
            parse_mode="Markdown",
        )


# ==========================================
# FEATURE: RELEASING
# ==========================================
def process_release_step(message):
    term = message.text.strip().upper()
    user_id = message.from_user.id

    if term.isdigit():
        rows_deleted = execute_query(
            "DELETE FROM caught_pokemon WHERE user_id = ? AND pokemon_id = ?",
            (user_id, int(term)),
        )
    else:
        rows_deleted = execute_query(
            "DELETE FROM caught_pokemon WHERE user_id = ? AND name = ?", (user_id, term)
        )

    if rows_deleted > 0:
        bot.send_message(
            message.chat.id,
            f"💨 **{term}** has been released back into the wild.",
            parse_mode="Markdown",
        )
    else:
        bot.send_message(
            message.chat.id,
            f"❓ Could not find **{term}** in your Pokédex.",
            parse_mode="Markdown",
        )


# ==========================================
# FEATURE: VIEW (PAGINATION)
# ==========================================
def handle_view(chat_id, page=0, message_id=None):
    count_records = execute_query(
        "SELECT COUNT(*) FROM caught_pokemon WHERE user_id = ?", (chat_id,), fetch=True
    )
    total_items = count_records[0][0] if count_records else 0

    if total_items == 0:
        bot.send_message(chat_id, "📭 Your Pokédex is completely empty!")
        return

    total_pages = math.ceil(total_items / ITEMS_PER_PAGE)
    if page < 0:
        page = 0
    if page >= total_pages:
        page = total_pages - 1

    offset = page * ITEMS_PER_PAGE
    records = execute_query(
        "SELECT pokemon_id, name FROM caught_pokemon WHERE user_id = ? ORDER BY pokemon_id ASC LIMIT ? OFFSET ?",
        (chat_id, ITEMS_PER_PAGE, offset),
        fetch=True,
    )

    dex_text = f"📜 *YOUR CAUGHT POKÉMON (Page {page + 1}/{total_pages})*\n〰️〰️〰️〰️〰️〰️〰️〰️〰️\n"
    for pid, name in records:
        dex_text += f"🔹 `#{pid:04d}` - **{name}**\n"

    markup = types.InlineKeyboardMarkup()
    nav_buttons = []

    if page > 0:
        nav_buttons.append(
            types.InlineKeyboardButton("⬅️ Prev", callback_data=f"page_view_{page - 1}")
        )
    if page < total_pages - 1:
        nav_buttons.append(
            types.InlineKeyboardButton("Next ➡️", callback_data=f"page_view_{page + 1}")
        )

    if nav_buttons:
        markup.row(*nav_buttons)

    markup.row(types.InlineKeyboardButton("🏠 Main Menu", callback_data="action_home"))

    if message_id:
        bot.edit_message_text(
            dex_text, chat_id, message_id, parse_mode="Markdown", reply_markup=markup
        )
    else:
        bot.send_message(chat_id, dex_text, parse_mode="Markdown", reply_markup=markup)


# ==========================================
# FEATURE: STATS
# ==========================================
def handle_stats(chat_id):
    records = execute_query(
        "SELECT COUNT(*) FROM caught_pokemon WHERE user_id = ?", (chat_id,), fetch=True
    )
    total = records[0][0] if records else 0
    bot.send_message(
        chat_id,
        f"📊 *YOUR PROGRESS*\nTotal Pokémon Caught: **{total}**",
        parse_mode="Markdown",
    )


# ==========================================
# MAIN LOOP
# ==========================================
if __name__ == "__main__":
    init_db()

    bot.set_my_commands(
        [
            BotCommand("start", "Boot up the Pokédex Menu"),
            BotCommand("catch", "Add a new caught Pokémon"),
            BotCommand("search", "Check if a Pokémon is caught"),
            BotCommand("release", "Remove a Pokémon by Name/ID"),
            BotCommand("view", "See your full Pokédex list"),
            BotCommand("stats", "Check your total completion"),
            BotCommand("help", "Learn how to use the bot"),
        ]
    )

    print("Phase 7 Online. Speed Mode activated (API calls removed).")
    bot.infinity_polling()
