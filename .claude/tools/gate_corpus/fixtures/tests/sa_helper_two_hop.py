import inspect

import bot


def test_helper_two_shape():
    assert "return" in inspect.getsource(bot.helper_two)
