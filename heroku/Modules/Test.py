# CopyLeft 2026 github.com/i-execute // i_execute.t.me
# Licensed under AGPLv3.

__version__ = (2, 1, 3)
# meta developer: Execute_forge.t.me
# meta banner: https://raw.githubusercontent.com/i-execute/Modules/main/Storage/Info/MetaBanner.jpeg

# (c) Dan Gazizullin, 2021-2023. This file is part of the Hikka Userbot: github.com/hikariatama/Hikka

import getpass
import logging
import os
import platform as lib_platform
import random
import time

from telethon.tl.types import Message
from telethon.types import InputMediaWebPage

from .. import loader, utils

logger = logging.getLogger(__name__)

DEBUG_MODS_DIR = os.path.join(utils.get_base_dir(), "debug_modules")

if not os.path.isdir(DEBUG_MODS_DIR):
    os.mkdir(DEBUG_MODS_DIR, mode=0o755)

for mod in os.scandir(DEBUG_MODS_DIR):
    os.remove(mod.path)

@loader.tds
class Test(loader.Module):
    """Perform operations based on userbot self-testing"""

    strings = {
        "name": "Tester",
        "configping": "Your custom text. You can use placeholders: {ping} - That's your ping. {uptime} - It's your uptime. {ping_hint} - This is the same hint as in the heroku module, it is chosen with random chance, also you can specify this hint in the config. You can use the {hostname} placeholder if you need the hostname of your server",
        "configpingph": "Custom placeholders: {}",
        "hint": "Set a hint",
        "ping_emoji": "Emoji that appears when ping does not increase significantly",
        "_cfg_rich_mode": "Show ping as a Rich message.",
        "banner_url": "Image for your ping, for example: Storage/PingCommand.png",
        "_cmd_doc_ping": "Test your userbot ping",
        "_cls_doc": "Perform operations based on userbot self-testing",
    }

    def __init__(self):
        self._memory = {}
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "force_send_all",
                False,
                (
                    " Do not touch, if you don't know what it does!\nBy default, "
                    " Heroku will try to determine, which client caused logs. E.g. there"
                    " is a module Testule installed on Client1 and Testule2 on"
                    " Client2. By default, Client2 will get logs from Testule2, and"
                    " Client1 will get logs from Testule. If this option is enabled,"
                    " this client will also receive logs, caused by other clients. It"
                    " affects this client only."
                ),
                validator=loader.validators.Boolean(),
                on_change=self._pass_config_to_logger,
            ),
            loader.ConfigValue(
                "tglog_level",
                "ERROR",
                (
                    " Do not touch, if you don't know what it does!\n"
                    "Minimal loglevel for records to be sent in Telegram."
                ),
                validator=loader.validators.Choice(
                    ["ALL", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL", "DISABLE"]
                ),
                on_change=self._pass_config_to_logger,
            ),
            loader.ConfigValue(
                "ignore_common",
                True,
                "Ignore common errors (e.g. 'TypeError' in telethon)",
                validator=loader.validators.Boolean(),
                on_change=self._pass_config_to_logger,
            ),
            loader.ConfigValue(
                "disable_internet_warn",
                False,
                "Ignore all internet errors",
                validator=loader.validators.Boolean(),
            ),
            loader.ConfigValue(
                "custom_message",
                " <b>𝙿𝚒𝚗𝚐: </b><code>{ping}</code><b> 𝚖𝚜 </b>\n<b> 𝚄𝚙𝚝𝚒𝚖𝚎: </b><code>{uptime}</code>",
                lambda: (
                    self.strings["configping"]
                    + (
                        "\n"
                        + self.strings["configpingph"].format(
                            "\n" + utils.config_placeholders()
                        )
                        if utils.config_placeholders()
                        else ""
                    )
                ),
                validator=loader.validators.String(),
            ),
            loader.ConfigValue(
                "hint",
                None,
                lambda: self.strings["hint"],
                validator=loader.validators.String(),
            ),
            loader.ConfigValue(
                "ping_emoji",
                "",
                lambda: self.strings["ping_emoji"],
                validator=loader.validators.String(),
            ),
            loader.ConfigValue(
                "banner_url",
                None,
                lambda: self.strings["banner_url"],
                validator=loader.validators.RandomLink(),
            ),
            loader.ConfigValue(
                "quote_media",
                False,
                "Switch preview media to quote in ping",
                validator=loader.validators.Boolean(),
            ),
            loader.ConfigValue(
                "rich_mode",
                False,
                lambda: self.strings["_cfg_rich_mode"],
                validator=loader.validators.Boolean(),
            ),
            loader.ConfigValue(
                "invert_media",
                False,
                "Switch preview invert media in ping",
                validator=loader.validators.Boolean(),
            ),
        )

    def _pass_config_to_logger(self):
        handler = logging.getLogger().handlers[0]
        handler.force_send_all = self.config["force_send_all"]
        handler.tg_level = {
            "ALL": 0,
            "DEBUG": 10,
            "INFO": 20,
            "WARNING": 30,
            "ERROR": 40,
            "CRITICAL": 50,
            "DISABLE": 50000,
        }[self.config["tglog_level"]]
        handler.ignore_common = self.config["ignore_common"]

    @loader.command()
    async def ping(self, message: Message):
        """- Find out your userbot ping"""
        start = time.perf_counter_ns()
        message = await utils.answer(message, "…")
        banner = str(self.config["banner_url"])

        if self.config["banner_url"] and self.config["quote_media"] is True:
            banner = InputMediaWebPage(str(self.config["banner_url"]), optional=True)

        elif not self.config["banner_url"]:
            banner = None

        data = {
            "ping": round((time.perf_counter_ns() - start) / 10**6, 3),
            "uptime": utils.formatted_uptime(),
            "ping_hint": (
                (self.config["hint"]) if random.choice([0, 0, 1]) == 1 else ""
            ),
            "hostname": lib_platform.node(),
            "user": getpass.getuser(),
            "platform": utils.get_platform_name(),
        }
        data = await utils.get_placeholders(data, self.config["custom_message"])
        try:
            placeholders_msg = self.config["custom_message"].format(**data)
        except KeyError:
            logger.exception("Missing placeholder in custom_message")
            placeholders_msg = ""
        if self.config["rich_mode"]:
            rich_message = placeholders_msg.replace("\r\n", "<br>").replace("\n", "<br>")
            await utils.answer(
                message,
                rich_message=rich_message,
            )
            return

        await utils.answer(
            message,
            placeholders_msg,
            file=banner,
            invert_media=self.config["invert_media"],
        )

    async def client_ready(self):
        self._content_channel_id = await utils.wait_for_content_channel(self._db)
        self.logchat = int(f"-100{self._content_channel_id}")
        logging.getLogger().handlers[0].install_tg_log(self)
        logger.debug("Bot logging installed for %s", self.logchat)

        self._pass_config_to_logger()
