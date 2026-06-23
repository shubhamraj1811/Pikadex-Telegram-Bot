import telebot
from telebot import types
from telebot.types import BotCommand
import sqlite3
import requests

# Paste your token here!
TOKEN = "8796049296:AAFaDg9UH-_3PeLTCxCnTwgLcu9Nu9Di90c"
bot = telebot.TeleBot(TOKEN)
DB_FILE = "rejuv_bot.db"

user_catch_data = {}


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
# SPRITE FETCHER
# ==========================================
def get_pokemon_sprite(name):
    try:
        response = requests.get(
            f"https://pokeapi.co/api/v2/pokemon/{name.lower()}", timeout=3
        )
        if response.status_code == 200:
            data = response.json()
            return data["sprites"]["front_default"]
    except requests.RequestException:
        pass
    return "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/items/poke-ball.png"


# ==========================================
# MAIN MENU & BUTTONS
# ==========================================
@bot.message_handler(commands=["start", "help"])
def send_welcome(message):
    welcome_text = (
        "🤖 *Rejuvenation Dex v5.0*\n\n"
        "Welcome back to Aevium! What would you like to do?"
    )

    markup = types.InlineKeyboardMarkup()
    btn_catch = types.InlineKeyboardButton("➕ Catch", callback_data="action_catch")
    btn_release = types.InlineKeyboardButton(
        "❌ Release", callback_data="action_release"
    )
    btn_view = types.InlineKeyboardButton("📜 View Dex", callback_data="action_view")
    btn_search = types.InlineKeyboardButton("🔍 Search", callback_data="action_search")
    btn_stats = types.InlineKeyboardButton("📊 Stats", callback_data="action_stats")

    # Custom Row Layout for better looks
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
            "Mistakes happen! Enter the **Name** or **ID** to release:",
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
        handle_view(chat_id)

    elif call.data == "action_stats":
        handle_stats(chat_id)


# ==========================================
# FEATURE: SEARCHING (NEW!)
# ==========================================
def process_search_step(message):
    if message.text.startswith("/"):
        bot.reply_to(message, "Action canceled.")
        return

    term = message.text.strip().upper()
    user_id = message.from_user.id

    # Check Database
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
        # It's caught! Fetch data and sprite.
        pid, name = result[0]
        bot.send_chat_action(message.chat.id, "upload_photo")
        sprite_url = get_pokemon_sprite(name)
        caption_text = (
            f"✅ *IN POKÉDEX!*\nYou have already caught **{name}** (ID: #{pid:04d})."
        )

        bot.send_photo(
            message.chat.id, sprite_url, caption=caption_text, parse_mode="Markdown"
        )
    else:
        # Not caught.
        bot.send_message(
            message.chat.id,
            f"❌ **{term}** is NOT in your Pokédex yet. Time to throw a Pokéball!",
            parse_mode="Markdown",
        )


# ==========================================
# FEATURE: CATCHING
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
            bot.send_chat_action(message.chat.id, "upload_photo")
            sprite_url = get_pokemon_sprite(name)
            caption_text = (
                f"✅ *Caught!*\nSuccessfully registered **{name}** (ID: #{pid:04d})."
            )
            bot.send_photo(
                message.chat.id, sprite_url, caption=caption_text, parse_mode="Markdown"
            )

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
# FEATURE: VIEW & STATS
# ==========================================
def handle_view(chat_id):
    records = execute_query(
        "SELECT pokemon_id, name FROM caught_pokemon WHERE user_id = ? ORDER BY pokemon_id ASC",
        (chat_id,),
        fetch=True,
    )

    if not records:
        bot.send_message(chat_id, "📭 Your Pokédex is completely empty!")
        return

    dex_text = "📜 *YOUR CAUGHT POKÉMON*\n〰️〰️〰️〰️〰️〰️〰️〰️〰️\n"
    for pid, name in records:
        dex_text += f"🔹 `#{pid:04d}` - **{name}**\n"

    bot.send_message(chat_id, dex_text, parse_mode="Markdown")


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

    # --- NEW CODE: Set up the Command Palette ---
    bot.set_my_commands(
        [
            BotCommand("start", "Boot up the Pokédex Menu"),
            BotCommand("help", "Learn how to use the bot"),
        ]
    )
    # --------------------------------------------

    print("Phase 5.1 Online. Command Menu integrated.")
    bot.infinity_polling()
