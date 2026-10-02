from telethon.tl.types import Message

from .. import loader, utils
from .._internal import restart as restart_process


@loader.tds
class Restart(loader.Module):
    strings = {
        "name": "Restart",
        "restarting": "<b>Restarting Heroku</b>\n<blockquote>The userbot will return shortly.</blockquote>",
    }

    @loader.owner
    @loader.command()
    async def restart(self, message: Message):
        await utils.answer(message, self.strings["restarting"])
        await self._client.disconnect()
        restart_process()
