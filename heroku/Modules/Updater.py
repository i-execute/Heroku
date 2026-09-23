# CopyLeft 2026 github.com/i-execute // i_execute.t.me
# Licensed under AGPLv3.

__version__ = (2, 1, 3)
# meta developer: Execute_forge.t.me
# meta banner: https://raw.githubusercontent.com/i-execute/Modules/main/Storage/Info/MetaBanner.jpeg

# (c) Dan Gazizullin, 2021-2023. This file is part of the Hikka Userbot: github.com/hikariatama/Hikka

import asyncio
import inspect
import json
import logging
import os
import subprocess
import sys
import time
import typing

import git
from git import Repo
from telethon.tl.types import (
    InputBotInlineMessageID,
    InputBotInlineMessageID64,
    Message,
)

from .. import loader, main, utils
from .._internal import restart
from ..inline.types import InlineCall

logger = logging.getLogger(__name__)
NO_GIT = os.environ.get("HEROKU_NO_GIT") == "1"

os.environ["GIT_TERMINAL_PROMPT"] = "0"
os.environ["GIT_ASKPASS"] = "echo"

@loader.tds
class Updater(loader.Module):
    """Updates itself, tracks latest Heroku releases, and notifies you, if update is required"""

    strings = {
        "name": "Updater",
        "restarting_caption": "<b>Your {} is restarting...</b>",
        "origin_cfg_doc": "Git origin URL, for where to update from",
        "btn_restart": "Restart",
        "cancel": "Cancel",
        "_cmd_doc_restart": "Restarts the userbot",
        "_cmd_doc_update": "Downloads userbot updates",
        "_cls_doc": "Updates itself, tracks latest Heroku releases, and notifies you, if update is required",
        "disabled": "<b>Userbot disabled.</b> Only <code>.enable</code> from the owner works now.",
        "enabled": "<b>Userbot enabled.</b>",
        "not_disabled": "<b>Userbot is not disabled.</b>",
        "restart_confirm": "<b>Are you sure you want to restart?</b>",
        "secure_boot_confirm": "<b>Are you sure you want to restart in secure boot mode?</b>",
    }
    _GIT_FETCH_INTERVAL = 300
    _EMFILE_FETCH_BACKOFF = 900

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "GIT_ORIGIN_URL",
                "https://github.com/i-execute/Heroku",
                lambda: self.strings["origin_cfg_doc"],
                validator=loader.validators.Link(),
            ),
        )

    @loader.command()
    async def restart(self, message: Message):
        args = utils.get_args_raw(message)
        secure_boot = any(trigger in args for trigger in {"--secure-boot", "-sb"})
        try:
            if (
                "-f" in args
                or not self.inline.init_complete
                or not await self.inline.form(
                    message=message,
                    text=self.strings[
                        "secure_boot_confirm" if secure_boot else "restart_confirm"
                    ],
                    reply_markup=[
                        {
                            "text": self.strings["btn_restart"],
                            "callback": self.inline_restart,
                            "args": (secure_boot,),
                            "style": "primary",
                        },
                        {
                            "text": self.strings["cancel"],
                            "action": "close",
                            "style": "primary",
                        },
                    ],
                )
            ):
                raise
        except Exception:
            await self.restart_common(message, secure_boot)

    async def inline_restart(self, call: InlineCall, secure_boot: bool = False):
        await self.restart_common(call, secure_boot=secure_boot)

    async def _kill_children(self):
        import psutil

        proc = psutil.Process()
        for child in proc.children(recursive=True):
            try:
                child.kill()
            except psutil.Error:
                pass

    def _live_loops(self) -> list:
        return [
            method
            for mod in self.allmodules.modules
            for _, method in utils.iter_attrs(mod)
            if isinstance(method, loader.InfiniteLoop) and method._task
        ]

    async def _fire_hooks(self, hook: str):
        await asyncio.gather(
            *[
                func(self.client, self._db)
                if len(inspect.signature(func).parameters) == 2
                else func()
                for mod in self.allmodules.modules
                if (func := getattr(mod, hook, None)) is not None
            ],
            return_exceptions=True,
        )

    @loader.command()
    async def disable(self, message: Message):
        """Kill everything except the watcher for .enable"""
        live = self._live_loops()

        self._db.set(main.__name__, "heroku_disabled", True)
        self._db.set(
            "heroku.disabled_loops",
            "modules",
            sorted({m.module_instance.__class__.__name__ for m in live}),
        )

        await utils.answer(message, self.strings["disabled"])

        await self._fire_hooks("on_disable")

        for loop in live:
            loop.stop()

        await self._kill_children()

    @loader.command()
    async def enable(self, message: Message):
        """Restore userbot after .disable"""
        if not self._db.get(main.__name__, "heroku_disabled", False):
            return await utils.answer(message, self.strings["not_disabled"])

        self._db.set(main.__name__, "heroku_disabled", False)

        saved = self._db.get("heroku.disabled_loops", "modules", [])
        for mod in self.allmodules.modules:
            if mod.__class__.__name__ not in saved:
                continue
            for _, method in utils.iter_attrs(mod):
                if isinstance(method, loader.InfiniteLoop):
                    if not method._task or method._task.done():
                        method.start()

        await self._fire_hooks("on_enable")
        await utils.answer(message, self.strings["enabled"])


    @staticmethod
    def _serialize_inline_message_id(
        inline_message_id: str | InputBotInlineMessageID | InputBotInlineMessageID64,
    ) -> str:
        if isinstance(
            inline_message_id,
            (InputBotInlineMessageID, InputBotInlineMessageID64),
        ):
            return typing.cast(str, inline_message_id.to_json())

        return inline_message_id

    @staticmethod
    def _deserialize_inline_message_id(
        inline_message_id: str,
    ) -> str | InputBotInlineMessageID | InputBotInlineMessageID64:
        try:
            data = json.loads(inline_message_id)
        except (TypeError, ValueError):
            return inline_message_id

        if not isinstance(data, dict):
            return inline_message_id

        if data.get("_") == "InputBotInlineMessageID":
            return InputBotInlineMessageID(
                dc_id=data["dc_id"],
                id=data["id"],
                access_hash=data["access_hash"],
            )

        if data.get("_") == "InputBotInlineMessageID64":
            return InputBotInlineMessageID64(
                dc_id=data["dc_id"],
                owner_id=data["owner_id"],
                id=data["id"],
                access_hash=data["access_hash"],
            )

        return inline_message_id

    @staticmethod
    def _parse_legacy_update_message_ref(
        message_ref: typing.Any,
    ) -> tuple[int, int] | None:
        if not isinstance(message_ref, str):
            return None

        parts = message_ref.split(":")
        if len(parts) != 2:
            return None

        try:
            return int(parts[0]), int(parts[1])
        except ValueError:
            return None

    async def process_restart_message(self, msg_obj: InlineCall | Message):
        inline_message_id = getattr(msg_obj, "inline_message_id", None)
        self.set(
            "selfupdatemsg",
            (
                self._serialize_inline_message_id(inline_message_id)
                if inline_message_id is not None
                else f"{utils.get_chat_id(msg_obj)}:{msg_obj.id}"
            ),
        )

    async def restart_common(
        self,
        msg_obj: InlineCall | Message,
        secure_boot: bool = False,
    ):
        if (
            hasattr(msg_obj, "form")
            and isinstance(msg_obj.form, dict)
            and "uid" in msg_obj.form
            and msg_obj.form["uid"] in self.inline._units
            and "message" in self.inline._units[msg_obj.form["uid"]]
        ):
            message = self.inline._units[msg_obj.form["uid"]]["message"]
        else:
            message = msg_obj

        if secure_boot:
            self._db.set(loader.__name__, "secure_boot", True)

        msg_obj = await utils.answer(
            msg_obj,
            self.strings["restarting_caption"].format(
                utils.get_platform_emoji()
                if self._client.heroku_me.premium
                else "Heroku"
            ),
        )

        await self.process_restart_message(msg_obj)

        self.db.set("Updater", "modules_count", len(self.allmodules.modules))

        self.set("restart_ts", time.time())

        handler = logging.getLogger().handlers[0]
        handler.setLevel(logging.CRITICAL)

        await message.client.disconnect()
        restart()

    async def download_common(self):
        def _sync():
            try:
                with Repo(os.path.dirname(utils.get_base_dir())) as repo:
                    origin = repo.remote("origin")
                    logger.debug("Fetching updates from %s", origin.url)
                    r = origin.pull()
                    new_commit = repo.head.commit
                    for info in r:
                        if info.old_commit:
                            for d in new_commit.diff(info.old_commit):
                                if d.b_path == "Storage/requirements.txt":
                                    return True
                return False
            except git.exc.InvalidGitRepositoryError:
                repo = Repo.init(os.path.dirname(utils.get_base_dir()))
                with repo:
                    origin = repo.create_remote("origin", self.config["GIT_ORIGIN_URL"])
                    logger.debug("Fetching initial updates from %s", origin.url)
                    origin.fetch()
                    repo.create_head("master", origin.refs.master)
                    repo.heads.master.set_tracking_branch(origin.refs.master)
                    repo.heads.master.checkout(True)
                return False

        return await asyncio.wait_for(
            asyncio.to_thread(_sync),
            timeout=120,
        )

    @staticmethod
    def req_common():

        logger.debug("Installing new requirements...")
        try:
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "-r",
                    os.path.join(
                        os.path.dirname(utils.get_base_dir()),
                        "Storage/requirements.txt",
                    ),
                    "--user",
                ],
                check=True,
                timeout=600,
                capture_output=True,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            logger.exception("Req install failed")

    @loader.command()
    async def update(self, message: Message):
        if NO_GIT:
            await utils.answer(
                message,
                "<b>Git disabled via --no-git.</b>",
            )
            return

        await self.inline_update(message)

    async def inline_update(
        self,
        msg_obj: InlineCall | Message,
        hard: bool = False,
    ):
        if NO_GIT:
            logger.warning("Git disabled via --no-git; update skipped")
            return
        try:
            if await self.download_common():
                await asyncio.to_thread(self.req_common)
            await self.restart_common(msg_obj)
        except Exception:
            logger.exception("Update failed")

