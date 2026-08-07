from telegram.constants import ParseMode


async def a_cmd(update, context):
    who = "x"
    await update.message.reply_text(f"hi {who}", parse_mode=ParseMode.MARKDOWN_V2)
