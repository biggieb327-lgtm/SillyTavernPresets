import inspect

import bot


def test_alpha_has_a_guard():
    assert "reply_text" in inspect.getsource(bot.alpha_cmd)
