from bot_app.services.action_schema import ActionRequest


class ChatHandler:
    def __init__(self, guards, memory, model, settings):
        self.guards = guards
        self.memory = memory
        self.model = model
        self.settings = settings

    async def handle_text(self, update, context):
        user = update.effective_user
        result = self.guards.check_user(user.id)
        if not result.ok:
            await update.message.reply_text(result.reason)
            return
        chat_id = update.effective_chat.id
        user_text = (update.message.text or "")[: self.settings.max_user_text_chars]
        history = self.memory.store.conversation_history.get(chat_id, [])
        system_blocks = [
            "You are a safe assistant. Never invent permissions.",
            self.memory.trusted_context_block(chat_id),
            self.memory.untrusted_context_block(chat_id),
        ]
        messages = self.model.build_messages(system_blocks, history, user_text)
        reply = self.model.request_reply(messages)
        action = ActionRequest(**reply.action)
        text = reply.text
        if not self.settings.model_side_effects_enabled or not action.valid() or action.action == "none":
            await update.message.reply_text(text)
        else:
            await update.message.reply_text(text)
        self.memory.remember_chat(chat_id, "user", user_text)
        self.memory.remember_chat(chat_id, "assistant", text)
