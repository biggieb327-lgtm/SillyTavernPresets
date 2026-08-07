async def a_cmd(update, context):
    name = "x"
    body = (
        f"line one {name}"
        "\nline two"
        "\nline three"
        "\nline four"
        "\nline five"
        "\nline six"
        "\nline seven"
        "\nline eight"
    )
    await update.message.reply_text(body, parse_mode="Markdown")
