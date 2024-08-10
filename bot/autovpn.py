import os

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler
from secrets import APP_TOKEN, MAGIC_WORD, AUTH_TTL, KEYS_PATH, SUPERUSER_ID, SCRIPT
from datetime import datetime
from os import path
from typing import List
import json
import subprocess


authorized_users = {}


def check_authorization(user_id) -> bool:
    if user_id in SUPERUSER_ID:
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
        f'/add <client> - Add a new client to the service\n'
        f'/remove <client> - Remove a client from the service\n'
        f'/list - List all clients\n'
        f'/get <client> - Get a key file of the client\n'
        f'/help - Show this help message\n')


async def display_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not check_authorization(update.effective_user.id):
        await unauthorized_error_message(update)
        return

    # Read KEYS_PATH directory and list all .ovpn files
    message = "List of users:\n<pre>"
    client_list = list_clients()
    count = len(client_list)

    index = 0
    for client in client_list:
        index += 1
        message += f"{index:02d}. {client}\n"

    message += "</pre>\n" + str(count) + " users in total."

    await update.message.reply_text(message, parse_mode="HTML")


def list_clients() -> List[str]:
    client_list = []
    for filename in os.listdir(KEYS_PATH):
        if filename.endswith(".ovpn"):
            client = filename.split(".ovpn")[0]
            if len(client) > 0:
                client_list.append(client)
    # Sort client
    client_list.sort()
    return client_list


def get_clients_keyboard(cmd: str = "get") -> InlineKeyboardMarkup:
    """Generates the base keyboard layout."""
    client_list = list_clients()
    keyboard = []

    for username in client_list:
        keyboard.append([InlineKeyboardButton(username, callback_data=json.dumps({"cmd": cmd, "client": username}))])

    return InlineKeyboardMarkup(keyboard)


async def get_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not check_authorization(update.effective_user.id):
        await unauthorized_error_message(update)
        return

    if len(context.args) == 0:
        await update.message.reply_text(f'Select from the list', reply_markup=get_clients_keyboard())
        return

    try:
        index = int(context.args[0])
    except ValueError:
        index = -1

    client_list = list_clients()

    if index > 0:
        if index > len(client_list):
            await update.message.reply_text(f'Client {index} not found.')
            return
        client = client_list[index - 1]

    else:
        client = context.args[0]

    await download_file(update.message, client)


async def download_file(message, client) -> None:
    if not path.exists(KEYS_PATH + client + ".ovpn"):
        await message.reply_text(f'Client {client} not found.')
        return
    await message.reply_document(open(KEYS_PATH + client + ".ovpn", 'rb'))


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
        await download_file(query.message, request['client'])
        return

    if request['cmd'] == 'remove':
        await query.edit_message_text(text=f'Are you sure you want to remove {request["client"]}?',
                                      reply_markup=get_remove_confirmation_buttons(request['client']))
        return

    if request['cmd'] == 'kill':
        result = _do_remove_client(request['client'])
        if result:
            await query.edit_message_text(text=f'User {request["client"]} removed.')
            return
        else:
            await query.edit_message_text(text=f'Error while removing user {request["client"]}')
            return

    if request['cmd'] == 'spare':
        await query.edit_message_text(text=f'OK, {request["client"]} stays here.')
        return

    await query.edit_message_text(text=f"Unknown request: {query.data}")


async def create_client(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not check_authorization(update.effective_user.id):
        await unauthorized_error_message(update)
        return

    if len(context.args) == 0:
        await update.message.reply_text(f'You have to specify a client name',
                                        reply_markup=get_clients_keyboard('remove'))
        return

    (result, message) = _do_create_client(context.args[0])
    if result:
        await download_file(update.message, context.args[0])
    else:
        await update.message.reply_text(message)


async def remove_client(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not check_authorization(update.effective_user.id):
        await unauthorized_error_message(update)
        return

    if len(context.args) == 0:
        await update.message.reply_text(f'Select from the list',
                                        reply_markup=get_clients_keyboard('remove'))
        return

    try:
        index = int(context.args[0])
    except ValueError:
        index = -1

    client_list = list_clients()

    if index > 0:
        if index > len(client_list):
            await update.message.reply_text(f'Client {index} not found.')
            return
        client = client_list[index - 1]

    else:
        client = context.args[0]

    await update.message.reply_text(
        f'Are you sure you want to remove {client}?',
        reply_markup=get_remove_confirmation_buttons(client))


def get_remove_confirmation_buttons(client) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(
            'Yes',
            callback_data=json.dumps({"cmd": "kill", "client": client})),
         InlineKeyboardButton(
                'No',
                callback_data=json.dumps({"cmd": "spare", "client": client}))]])


def _do_create_client(client: str) -> (bool, str):
    if not path.exists(SCRIPT):
        return False, f"Error: {SCRIPT} not found."

    try:
        proc = subprocess.run([SCRIPT, "-u", client], check=True)
    except subprocess.CalledProcessError as e:
        return False, f"Exec error: {e}"

    if proc.returncode != 0:
        return False, f"Error code {proc.returncode}"

    return True, "OK"


def _do_remove_client(client: str) -> (bool, str):
    if not path.exists(SCRIPT):
        return False, f"Error: {SCRIPT} not found."
    try:
        proc = subprocess.run([SCRIPT, "-r", client], check=True)
    except subprocess.CalledProcessError as e:
        return False, f"Exec error: {e}"

    if proc.returncode != 0:
        return False, f"Error code {proc.returncode}"

    return True, "OK"


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
app.add_handler(CommandHandler("remove", remove_client))
app.add_handler(CommandHandler("add", create_client))
app.add_handler(CommandHandler("myid", display_my_id))
app.add_handler(CallbackQueryHandler(process_button))

app.run_polling()
