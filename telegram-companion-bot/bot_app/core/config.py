from dataclasses import dataclass
import os


def _flag(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    bot_token: str = os.getenv("BOT_TOKEN", "")
    model_side_effects_enabled: bool = _flag("MODEL_SIDE_EFFECTS_ENABLED", "0")
    strict_memory_mode: bool = _flag("STRICT_MEMORY_MODE", "1")
    max_user_text_chars: int = int(os.getenv("MAX_USER_TEXT_CHARS", "4000"))
    max_memory_item_chars: int = int(os.getenv("MAX_MEMORY_ITEM_CHARS", "500"))
    max_untrusted_notes: int = int(os.getenv("MAX_UNTRUSTED_NOTES", "60"))
    ffmpeg_timeout: int = int(os.getenv("FFMPEG_TIMEOUT", "25"))
