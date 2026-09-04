"""Admin API bind must degrade on port clash, not crash startup."""
import asyncio
from unittest.mock import MagicMock, patch

import bot


def test_start_admin_api_bind_failure_degrades_without_raising():
    """ROADMAP 1.2: second instance on the same ADMIN_API_PORT must not die at bind."""
    with patch.object(bot, "ADMIN_API_ENABLED", True), \
         patch.object(bot, "ADMIN_API_TOKEN", "test-token-not-a-secret"), \
         patch.object(bot, "ADMIN_API_BIND", "127.0.0.1"), \
         patch.object(bot, "ADMIN_API_PORT", 8765), \
         patch.object(bot, "_admin_httpd", None), \
         patch("bot.http.server.ThreadingHTTPServer", side_effect=OSError("Address already in use")), \
         patch("bot.threading.Thread") as thread_cls:
        asyncio.run(bot._start_admin_api(MagicMock()))
        thread_cls.assert_not_called()
        assert bot._admin_httpd is None


def test_start_admin_api_success_starts_daemon_thread():
    fake_httpd = MagicMock()
    with patch.object(bot, "ADMIN_API_ENABLED", True), \
         patch.object(bot, "ADMIN_API_TOKEN", "test-token-not-a-secret"), \
         patch.object(bot, "ADMIN_API_BIND", "127.0.0.1"), \
         patch.object(bot, "ADMIN_API_PORT", 18080), \
         patch.object(bot, "_admin_httpd", None), \
         patch("bot.http.server.ThreadingHTTPServer", return_value=fake_httpd) as server_cls, \
         patch("bot.threading.Thread") as thread_cls:
        thread = MagicMock()
        thread_cls.return_value = thread
        asyncio.run(bot._start_admin_api(MagicMock()))
        server_cls.assert_called_once()
        thread_cls.assert_called_once()
        assert thread_cls.call_args.kwargs.get("daemon") is True
        thread.start.assert_called_once()
        assert bot._admin_httpd is fake_httpd
