# CopyLeft 2026 github.com/i-execute // i_execute.t.me
# Licensed under AGPLv3.

__version__ = (2, 1, 3)
# meta developer: Execute_forge.t.me
# meta banner: https://raw.githubusercontent.com/i-execute/Modules/main/Storage/Info/MetaBanner.jpeg

# (c) Dan Gazizullin, 2021-2023. This file is part of the Hikka Userbot: github.com/hikariatama/Hikka

import asyncio
import contextlib
import datetime
import io
import logging
import os
import time
import zipfile
import orjson
import requests

from pathlib import Path

from telethon.tl.types import Message

from .. import loader, utils

logger = logging.getLogger(__name__)

@loader.tds
class Backup(loader.Module):
    """Handles database and modules backups"""

    strings = {
        "name": "Backup",
        "backupall_info": "<b>This is your backup of the database and modules. Do not give it to anyone, it contains personal information. If you need to restore it, use</b> <pre><code class=\"language-heroku\">{prefix}restoreall</code></pre> <b>in response to this file.</b>",
        "restoring_backup": "<b>Restoring backup, installing dependencies and modules...</b>",
        "all_restored": "<b>Your full backup has been restored, restarting...</b>",
        "reply_to_file": "<b>Reply with.json or.zip file</b>",
        "db_restored": "<b>Database updated, restarting...</b>",
        "backupall_sent": "<b>Backup of database and modules sent to <a href={}>database chat</a></b>",
        "_cls_doc": "Processes database and module backups",
    }

    async def client_ready(self):
        self._content_channel_id = await utils.wait_for_content_channel(self._db)


    @loader.loop(interval=1, autostart=True)
    async def handler(self):
        try:
            period = self.lookup("Settings").config["backup_period"]
            if not period:
                await asyncio.sleep(3)
                return

            period *= 3600

            if not self.get("last_backup"):
                self.set("last_backup", round(time.time()))
                await asyncio.sleep(period)
                return

            await asyncio.sleep(
                self.get("last_backup") + period - time.time()
            )

            db = io.BytesIO(
                orjson.dumps(
                    self._db, option=orjson.OPT_INDENT_2 | orjson.OPT_NON_STR_KEYS
                )
            )
            db.name = "db.json"

            mods = io.BytesIO()
            with zipfile.ZipFile(mods, "w", zipfile.ZIP_DEFLATED) as zipf:
                for root, _, files in os.walk(loader.LOADED_MODULES_DIR):
                    for file in files:
                        if file.endswith(".py"):
                            with open(os.path.join(root, file), "rb") as f:
                                zipf.writestr(file, f.read())

            mods.seek(0)
            mods.name = "mods.zip"

            archive = io.BytesIO()
            with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
                z.writestr("db.json", db.getvalue())
                z.writestr("mods.zip", mods.getvalue())

            archive.name = f"backup-{datetime.datetime.now():%d-%m-%Y-%H-%M}.backup"

            backup_topic_id = await utils.get_topic_id(self._db, "Backups")
            if not backup_topic_id:
                logger.error("Backups topic not found in database")
                return

            await self.inline.bot.send_document(
                int(f"-100{self._content_channel_id}"),
                archive,
                reply_markup=self.inline.generate_markup(
                    [
                        [
                            {
                                "text": " Restore this",
                                "data": "heroku/backupall/restore/confirm",
                                "style": "primary",
                            }
                        ]
                    ]
                ),
                message_thread_id=backup_topic_id,
            )

            self.set("last_backup", round(time.time()))
        except loader.StopLoop:
            raise
        except Exception:
            logger.exception("Backup failed")
            await asyncio.sleep(60)

    @loader.command()
    async def backup(self, message: Message):
        """Create full backup (db + modules) as .backup archive"""
        db = io.BytesIO(
            orjson.dumps(self._db, option=orjson.OPT_INDENT_2 | orjson.OPT_NON_STR_KEYS)
        )
        db.name = "db.json"

        mods = io.BytesIO()
        with zipfile.ZipFile(mods, "w", zipfile.ZIP_DEFLATED) as zipf:
            for root, _, files in os.walk(loader.LOADED_MODULES_DIR):
                for file in files:
                    if file.endswith(".py"):
                        with open(os.path.join(root, file), "rb") as f:
                            zipf.writestr(file, f.read())

        mods.seek(0)
        mods.name = "mods.zip"

        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("db.json", db.getvalue())
            z.writestr("mods.zip", mods.getvalue())

        archive.name = f"heroku-{datetime.datetime.now():%d-%m-%Y-%H-%M}.backup"

        backup_topic_id = await utils.get_topic_id(self._db, "Backups")
        if not backup_topic_id:
            logger.error("Backups topic not found in database")
            await utils.answer(
                message,
                "<b>Backups topic not found in database.</b>",
            )
            return

        backup_msg = await self.inline.bot.send_document(
            int(f"-100{self._content_channel_id}"),
            archive,
            caption=self.strings["backupall_info"].format(
                prefix=utils.escape_html(self.get_prefix()),
            ),
            message_thread_id=backup_topic_id,
        )

        await utils.answer(
            message,
            self.strings["backupall_sent"].format(
                f"https://t.me/c/{self._content_channel_id}/{backup_topic_id}/{self._message_id(backup_msg)}"
            ),
        )

    @loader.command()
    async def restore(self, message: Message):
        """Restore database (reply to .json) or full backup (reply to .backup archive)"""
        if not (reply := await message.get_reply_message()) or not reply.media:
            await utils.answer(message, self.strings["reply_to_file"])
            return

        file = await reply.download_media(bytes)

        try:
            decoded_text = orjson.loads(file.decode())
        except (UnicodeDecodeError, orjson.JSONDecodeError):
            decoded_text = None

        if decoded_text is not None:
            with contextlib.suppress(KeyError):
                decoded_text["heroku.inline"].pop("bot_token")

            if not self._db.process_db_autofix(decoded_text):
                raise RuntimeError("Attempted to restore broken database")

            self._db.clear()
            self._db.update(**decoded_text)
            self._db.save()

            await utils.answer(message, self.strings["db_restored"])
            await self.invoke("restart", "-f", peer=message.peer_id)
            return

        status_message = await utils.answer(message, self.strings["restoring_backup"])
        try:
            zipfile_bytes = io.BytesIO(file)
            with zipfile.ZipFile(zipfile_bytes) as zf:
                with zf.open("db.json") as f:
                    db_data = orjson.loads(f.read().decode())

                with contextlib.suppress(KeyError):
                    db_data["heroku.inline"].pop("bot_token")

                if not self._db.process_db_autofix(db_data):
                    raise RuntimeError("Attempted to restore broken database")

                self._db.clear()
                self._db.update(**db_data)
                self._db.save()

                if "mods.zip" in zf.namelist():
                    with zf.open("mods.zip") as modzip_bytes:
                        with zipfile.ZipFile(io.BytesIO(modzip_bytes.read())) as modzip:
                            names = modzip.namelist()
                            for name in names:
                                if not Path(name).name.endswith(".py"):
                                    continue

                                path = loader.LOADED_MODULES_PATH / Path(name).name
                                with modzip.open(name, "r") as module:
                                    path.write_bytes(module.read())

                            if "db_mods.json" in names:
                                links = orjson.loads(modzip.read("db_mods.json"))
                                fetched = skipped = 0
                                for mod, url in links.items():
                                    if (
                                        loader.LOADED_MODULES_PATH
                                        / f"{mod}.py"
                                    ).exists():
                                        continue
                                    try:
                                        r = await utils.run_sync(
                                            requests.get, url, timeout=30
                                        )
                                        r.raise_for_status()
                                        (
                                            loader.LOADED_MODULES_PATH / f"{mod}.py"
                                        ).write_bytes(r.content)
                                        fetched += 1
                                    except Exception as e:
                                        skipped += 1
                                        logger.warning(
                                            "restore: failed to fetch %s from %s: %s",
                                            mod,
                                            url,
                                            e,
                                        )
                                logger.info(
                                    "restore: fetched %d modules by url, %d failed",
                                    fetched,
                                    skipped,
                                )
        except Exception:
            logger.exception("Restore failed")
            await utils.answer(status_message, self.strings["reply_to_file"])
            return

        await utils.answer(status_message, self.strings["all_restored"])
        await self.invoke("restart", "-f", peer=message.peer_id)

