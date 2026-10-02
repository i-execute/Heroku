import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class FakeUpdate:
    def __init__(self, query, user_id=222):
        self.query = query
        self.user_id = user_id


class FakeBot:
    def __init__(self):
        self.chat_id = 111
        self.owner_id = 222
        self._ask_state = None


async def main():
    from heroku.botpm import BotPM

    loop = asyncio.get_running_loop()


    fut = loop.create_future()
    bot = FakeBot()
    bot._ask_state = ("ab12cd34", fut)
    await BotPM._on_inline_send(bot, FakeUpdate("ab12cd34 hunter2"))
    assert fut.done(), "picked article must resolve ask()"
    assert fut.result() == "hunter2", fut.result()


    fut = loop.create_future()
    bot._ask_state = ("tok", fut)
    await BotPM._on_inline_send(bot, FakeUpdate("tok my long pass phrase"))
    assert fut.result() == "my long pass phrase", fut.result()


    bot._ask_state = None
    await BotPM._on_inline_send(bot, FakeUpdate("tok whatever"))


    fut = loop.create_future()
    bot._ask_state = ("tok", fut)
    await BotPM._on_inline_send(bot, FakeUpdate("othertoken secret"))
    assert not fut.done(), "token mismatch must not resolve"


    fut = loop.create_future()
    bot._ask_state = ("tok", fut)
    await BotPM._on_inline_send(bot, FakeUpdate("tok"))
    assert not fut.done(), "bare token must not resolve"

    print("ask() inline-send contract OK")


if __name__ == "__main__":
    asyncio.run(main())
