class MediaHandler:
    def __init__(self, guards, memory):
        self.guards = guards
        self.memory = memory

    async def handle_photo_caption(self, update, context, caption: str = ""):
        user = update.effective_user
        result = self.guards.check_user(user.id)
        if not result.ok:
            await update.message.reply_text(result.reason)
            return
        chat_id = update.effective_chat.id
        if caption:
            self.memory.append_untrusted(chat_id, "photo", caption)
        await update.message.reply_text("Photo received.")

    async def handle_video_caption(self, update, context, caption: str = ""):
        user = update.effective_user
        result = self.guards.check_user(user.id)
        if not result.ok:
            await update.message.reply_text(result.reason)
            return
        chat_id = update.effective_chat.id
        if caption:
            self.memory.append_untrusted(chat_id, "video", caption)
        await update.message.reply_text("Video received.")
