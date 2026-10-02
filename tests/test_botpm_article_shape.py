import asyncio
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class Article:
    def __init__(self, title, description, article_id, text):
        self.title = title
        self.description = description
        self.id = article_id
        self.text = text


class FakeBuilder:
    async def article(
        self,
        title,
        description=None,
        *,
        id=None,
        text=None,
        parse_mode=(),
        **kwargs,
    ):
        return Article(title, description, id, text)


class FakeEvent:
    def __init__(self, query_text, user_id=222):
        class Query:
            pass

        query = Query()
        query.user_id = user_id
        self.query = query
        self.text = query_text
        self.builder = FakeBuilder()

    async def answer(self, results, **kwargs):
        self.answered = results


class FakeBot:
    def __init__(self):
        self.owner_id = 222
        self._ask_state = None


async def main():
    from heroku.botpm import BotPM

    bot = FakeBot()
    future = asyncio.get_running_loop().create_future()
    bot._ask_state = ("ab12cd34", future, "Enter password", "🔐")
    event = FakeEvent("ab12cd34 hunter2")
    await BotPM._on_iq(bot, event)
    article = event.answered[0]
    assert article.id == hashlib.sha256(b"ab12cd34 hunter2").hexdigest()
    assert "hunter2" not in article.id
    assert article.title == "Enter password"
    assert article.description == "Enter password"
    assert article.text == "🔐"

    foreign = FakeEvent("othertok whatever")
    bot._ask_state = ("ab12cd34", future, "Enter phone", "📝")
    await BotPM._on_iq(bot, foreign)
    assert not hasattr(foreign, "answered")


if __name__ == "__main__":
    asyncio.run(main())
