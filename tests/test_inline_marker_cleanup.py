import asyncio
import importlib
import struct
import sys
from pathlib import Path
from types import SimpleNamespace

from telethon.tl.types import PeerChannel

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

importlib.import_module("heroku.main")
Events = importlib.import_module("heroku.inline.events").Events


class Client:
    def __init__(self):
        self.text = "\u2063"
        self.deleted = []

    async def get_messages(self, peer, ids):
        return SimpleNamespace(raw_text=self.text)

    async def delete_messages(self, peer, ids):
        self.deleted.append((peer, ids))


async def main():
    manager = Events()
    manager._client = Client()
    private = SimpleNamespace(owner_id=123, id=44)
    assert manager._inline_message_location(private) == (None, 44)
    channel = SimpleNamespace(owner_id=-123, id=45)
    peer, message_id = manager._inline_message_location(channel)
    assert isinstance(peer, PeerChannel)
    assert peer.channel_id == 123
    assert message_id == 45
    legacy_id = struct.unpack("<q", struct.pack("<ii", 46, -124))[0]
    peer, message_id = manager._inline_message_location(
        SimpleNamespace(id=legacy_id)
    )
    assert isinstance(peer, PeerChannel)
    assert peer.channel_id == 124
    assert message_id == 46
    await manager._delete_inline_input_marker(private)
    assert manager._client.deleted == [(None, [44])]
    manager._client.text = "edited"
    await manager._delete_inline_input_marker(private)
    assert manager._client.deleted == [(None, [44])]


asyncio.run(main())
