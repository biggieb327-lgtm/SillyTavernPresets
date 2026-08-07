async def a_cmd(update, context):
    if not _is_admin(update.effective_user.id):
        return
    await update.message.reply_text("ok")
