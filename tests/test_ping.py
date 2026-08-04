from ht_manager.bot.commands.ping import ping_reply


def test_ping_reply_formats_milliseconds():
    assert ping_reply(0.123) == "Pong! 123ms"


def test_ping_reply_handles_zero_latency():
    assert ping_reply(0.0) == "Pong! 0ms"
