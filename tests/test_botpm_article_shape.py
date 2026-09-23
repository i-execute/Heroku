"""_on_iq builds the article exactly the way InlineBuilder accepts it."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))



class Article:
    def __init__(self, title, description, id):
        self.title = title
        self.description = description
        self.id = id


class FakeBuilder:
    """Records how the article() call is shaped."""

    async def article(self, title, description=None, *, id=None, text=None, parse_mode=(), **kw):
        return Article(title, description, id)


class FakeEvent:
    def __init__(self, query_text, user_id=222):
        class Q:
            pass

        q = Q()
        q.user_id = user_id
        self.query = q
        self.text = query_text
        self.builder = FakeBuilder()

    async def answer(self, results, **kw):
        self.answered = results


class FakeBot:
    def __init__(self):
        self.owner_id = 222
        self._ask_state = None


async def main():
    from heroku.botpm import BotPM

    # token + value -> article id must be the WHOLE query
    bot = FakeBot()
    fut = asyncio.get_running_loop().create_future()
    bot._ask_state = ("ab12cd34", fut)
    ev = FakeEvent("ab12cd34 hunter2")
    await BotPM._on_iq(bot, ev)
    assert ev.answered[0].id == "ab12cd34 hunter2", ev.answered[0].id

    # bare token -> still answered (empty value); foreign token -> not answered
    ev2 = FakeEvent("othertok whatever")
    bot._ask_state = ("ab12cd34", fut)
    await BotPM._on_iq(bot, ev2)
    assert not hasattr(ev2, "answered"), "foreign token must not answer"

    print("article() shape OK")


if __name__ == "__main__":
    asyncio.run(main())
