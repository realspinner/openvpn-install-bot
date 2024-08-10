import os

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler
from secrets import APP_TOKEN, MAGIC_WORD, AUTH_TTL, KEYS_PATH, SUPERUSER_ID
from datetime import datetime
from os import path
from typing import List
import json


authorized_users = {}


def check_authorization(user_id) -> bool:
    if user_id == SUPERUSER_ID:
        return True

    if user_id in authorized_users.keys():
        interval = datetime.now() - authorized_users[user_id]
        if interval.seconds < AUTH_TTL:
            authorized_users[user_id] = datetime.now()
            return True
    return False


def add_authorized_user(user_id):
    authorized_users[user_id] = datetime.now()


async def unauthorized_error_message(update: Update) -> None:
    await update.message.reply_text(
        f'I do not remember you, {update.effective_user.first_name}.\n'
        f'Use /login <magicword> to access the other commands.')


async def display_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not check_authorization(update.effective_user.id):
        await unauthorized_error_message(update)
        return

    await update.message.reply_text(
        f'List of commands:\n'
        f'/add <username> - Add a new user to the service\n'
        f'/remove <username> - Remove a user from the service\n'
        f'/list - List all users\n'
        f'/get <username> - Get a key file of the user\n'
        f'/help - Show this help message\n')


async def display_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not check_authorization(update.effective_user.id):
        await unauthorized_error_message(update)
        return

    # Read KEYS_PATH directory and list all .ovpn files
    message = "List of users:\n<pre>"
    userlist = list_users()
    count = len(userlist)

    index = 0
    for username in userlist:
        index += 1
        message += f"{index:02d}. {username}\n"

    message += "</pre>\n" + str(count) + " users in total."

    await update.message.reply_text(message, parse_mode="HTML")


def list_users() -> List[str]:
    user_list = []
    for filename in os.listdir(KEYS_PATH):
        if filename.endswith(".ovpn"):
            username = filename.split(".ovpn")[0]
            if len(username) > 0:
                user_list.append(username)
    # Sort userlist
    user_list.sort()
    return user_list


def get_userlist_keyboard(cmd: str = "get") -> InlineKeyboardMarkup:
    """Generates the base keyboard layout."""
    user_list = list_users()
    keyboard = []

    for username in user_list:
        keyboard.append([InlineKeyboardButton(username, callback_data=json.dumps({"cmd": cmd, "username": username}))])

    return InlineKeyboardMarkup(keyboard)


async def get_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not check_authorization(update.effective_user.id):
        await unauthorized_error_message(update)
        return

    if len(context.args) == 0:
        await update.message.reply_text(f'Select from the list', reply_markup=get_userlist_keyboard())
        return

    try:
        index = int(context.args[0])
    except ValueError:
        index = -1

    user_list = list_users()

    if index > 0:
        if index > len(user_list):
            await update.message.reply_text(f'User {index} not found.')
            return
        username = user_list[index - 1]

    else:
        username = context.args[0]

    await download_file(update.message, username)


async def download_file(message, username) -> None:
    if not path.exists(KEYS_PATH + username + ".ovpn"):
        await message.reply_text(f'User {username} not found.')
        return
    await message.reply_document(open(KEYS_PATH + username + ".ovpn", 'rb'))


async def process_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Parses the CallbackQuery and updates the message text."""
    query = update.callback_query

    # CallbackQueries need to be answered, even if no notification to the user is needed
    # Some clients may have trouble otherwise. See https://core.telegram.org/bots/api#callbackquery
    await query.answer()

    try:
        request = json.loads(query.data)
    except json.decoder.JSONDecodeError:
        request = None

    if request is None:
        await query.edit_message_text(text=f"Error while processing button request: {query.data}")
        return

    if request['cmd'] == 'get':
        await download_file(query.message, request['username'])
        return

    if request['cmd'] == 'remove':
        await query.edit_message_text(text=f'Are you sure you want to remove {request["username"]}?',
                                      reply_markup=get_remove_confirmation_buttons(request['username']))
        return

    if request['cmd'] == 'kill':
        result = _do_remove_user(request['username'])
        if result:
            await query.edit_message_text(text=f'User {request["username"]} removed.')
            return
        else:
            await query.edit_message_text(text=f'Error while removing user {request["username"]}')
            return

    if request['cmd'] == 'spare':
        await query.edit_message_text(text=f'OK, {request["username"]} stays here.')
        return

    await query.edit_message_text(text=f"Unknown request: {query.data}")


async def create_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    pass


async def remove_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not check_authorization(update.effective_user.id):
        await unauthorized_error_message(update)
        return

    if len(context.args) == 0:
        await update.message.reply_text(f'Select from the list',
                                        reply_markup=get_userlist_keyboard('remove'))
        return

    try:
        index = int(context.args[0])
    except ValueError:
        index = -1

    user_list = list_users()

    if index > 0:
        if index > len(user_list):
            await update.message.reply_text(f'User {index} not found.')
            return
        username = user_list[index - 1]

    else:
        username = context.args[0]

    await update.message.reply_text(
        f'Are you sure you want to remove {username}?',
        reply_markup=get_remove_confirmation_buttons(username))


def get_remove_confirmation_buttons(username) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(
            'Yes',
            callback_data=json.dumps({"cmd": "kill", "username": username})),
         InlineKeyboardButton(
                'No',
                callback_data=json.dumps({"cmd": "spare", "username": username}))]])


def _do_add_user(username: str) -> bool:
    pass


def _do_remove_user(username: str) -> bool:
    return True


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if check_authorization(update.effective_user.id):
        await update.message.reply_text(f'Hello {update.effective_user.first_name}!\n'
                                        f'Use /help to see the list of commands.')
    else:
        await update.message.reply_text(f'Hello {update.effective_user.first_name}!\n'
                                        f'Use /login <magicword> to access the other commands.')


async def display_my_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f'Your ID: {update.effective_user.id}')


async def login(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) == 0:
        await update.message.reply_text(f'You must say the magic word, pal.')
        return

    if context.args[0] == MAGIC_WORD:
        add_authorized_user(update.effective_user.id)
        await update.message.reply_text(f'{update.effective_user.first_name}, you\'ve got the access!\n'
                                        f'Use /help to see the list of commands.')
    else:
        await update.message.reply_text(f'Wrong magic word, pal. Your username has been reported to the bootsman.')


app = ApplicationBuilder().token(APP_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("login", login))
app.add_handler(CommandHandler("help", display_help))
app.add_handler(CommandHandler("list", display_list))
app.add_handler(CommandHandler("get", get_file))
app.add_handler(CommandHandler("remove", remove_user))
app.add_handler(CommandHandler("myid", display_my_id))
app.add_handler(CallbackQueryHandler(process_button))

app.run_polling()
