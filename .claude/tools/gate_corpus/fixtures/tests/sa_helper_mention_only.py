import inspect

import bot


def test_helper_one_shape():
    assert "helper_two" in inspect.getsource(bot.helper_one)
