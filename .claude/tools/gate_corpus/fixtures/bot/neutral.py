"""Neutral bot fixture: valid Python, no finding for any scanner."""
import os
from pathlib import Path

BASE_DIR = Path(os.getenv("BOT_HOME", ".")).resolve()


async def quiet_cmd(update, context):
    if not _is_admin(update.effective_user.id):
        return
    await update.message.reply_text("ok")
