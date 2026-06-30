class DocumentHandler:
    def __init__(self, guards, memory, ingestion):
        self.guards = guards
        self.memory = memory
        self.ingestion = ingestion

    async def handle_json_document(self, update, context, raw_bytes: bytes, filename: str):
        user = update.effective_user
        result = self.guards.check_user(user.id)
        if not result.ok:
            await update.message.reply_text(result.reason)
            return
        chat_id = update.effective_chat.id
        data = self.ingestion.parse_json_bytes(raw_bytes)
        summary = self.ingestion.summarize_document(filename, data)
        self.memory.append_untrusted(chat_id, f"json:{filename}", summary)
        await update.message.reply_text("Document imported into untrusted notes.")
