async def a_cmd(update, context):
    await update.message.reply_text("working")

    def _check(items):
        if len(items) < 2:
            return []
        return items

    _check(context.args or [])
