async def alpha_cmd(update, context):
    data = helper_one()
    await update.message.reply_text(data)


def helper_one():
    return helper_two()


def helper_two():
    return "b"
