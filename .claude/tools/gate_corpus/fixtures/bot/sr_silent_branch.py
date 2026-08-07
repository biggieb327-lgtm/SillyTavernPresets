async def a_cmd(update, context):
    items = context.args or []
    if len(items) < 2:
        return
    await update.message.reply_text("ok")
