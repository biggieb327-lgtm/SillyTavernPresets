def _reply_budget_ok(chat_id):
    return False


async def a_cmd(update, context):
    if not _reply_budget_ok(update.effective_chat.id):
        return
    await update.message.reply_text("ok")
