from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from secrets import APP_TOKEN


async def login(update: Update, constext: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f'Hello {update.effective_user.first_name}!')


app = ApplicationBuilder().token(APP_TOKEN).build()

app.add_handler(CommandHandler("login", login))

app.run_polling()
