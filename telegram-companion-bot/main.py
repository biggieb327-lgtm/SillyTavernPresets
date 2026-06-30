from bot_app.core.config import Settings
from bot_app.core.guards import GuardService
from bot_app.services.memory import MemoryService
from bot_app.services.model_api import ModelService
from bot_app.services.ingestion import IngestionService
from bot_app.handlers.chat import ChatHandler
from bot_app.handlers.documents import DocumentHandler
from bot_app.handlers.media import MediaHandler


def build_app(is_allowed_fn=None, rate_ok_fn=None):
    settings = Settings()
    guards = GuardService(is_allowed_fn=is_allowed_fn, rate_ok_fn=rate_ok_fn)
    memory = MemoryService(
        max_item_chars=settings.max_memory_item_chars,
        max_untrusted_notes=settings.max_untrusted_notes,
    )
    model = ModelService()
    ingestion = IngestionService()
    return {
        "settings": settings,
        "guards": guards,
        "memory": memory,
        "chat": ChatHandler(guards, memory, model, settings),
        "documents": DocumentHandler(guards, memory, ingestion),
        "media": MediaHandler(guards, memory),
    }


if __name__ == "__main__":
    app = build_app()
    print("Refactor starter initialized.")
