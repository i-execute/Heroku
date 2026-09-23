# CopyLeft 2026 github.com/i-execute // i_execute.t.me
# Licensed under AGPLv3.

# (c) Dan Gazizullin, 2021-2023. This file is part of the Hikka Userbot: github.com/hikariatama/Hikka

import argparse
import asyncio
import collections
import contextlib
import importlib
import json
import logging
import os
import random
import shutil
import signal
import sqlite3
import sys
import traceback
from pathlib import Path

from telethon import events
from telethon.errors import (
    ApiIdInvalidError,
    AuthKeyDuplicatedError,
)
from telethon.errors.rpcerrorlist import AuthKeyUnregisteredError
from telethon.network.connection import (
    ConnectionTcpFull,
)
from telethon.sessions import MemorySession, SQLiteSession

from . import database, loader, utils, version
from ._internal import (
    client_id_ctx,
    client_id_override,
    install_task_tracking,
    restart,
    set_client_id,
)
from .dispatcher import CommandDispatcher
from .tl_cache import CustomTelegramClient
from .version import __version__

BASE_DIR = (
    "/data"
    if "DOCKER" in os.environ
    else os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
)

BASE_PATH = Path(BASE_DIR)
CONFIG_PATH = BASE_PATH / "config.json"
SESSIONS_DIR = os.path.join(BASE_DIR, "sessions")
_CONFIG_CACHE: dict | None = None
_CONFIG_MTIME_NS: int | None = None

LATIN_MOCK = [
    "Amor", "Arbor", "Astra", "Aurum", "Bellum", "Caelum",
    "Calor", "Candor", "Carpe", "Celer", "Certo", "Cibus",
    "Civis", "Clemens", "Coetus", "Cogito", "Conexus",
    "Consilium", "Cresco", "Cura", "Cursus", "Decus",
    "Deus", "Dies", "Digitus", "Discipulus", "Dominus",
    "Donum", "Dulcis", "Durus", "Elementum", "Emendo",
    "Ensis", "Equus", "Espero", "Fidelis", "Fides",
    "Finis", "Flamma", "Flos", "Fortis", "Frater", "Fuga",
    "Fulgeo", "Genius", "Gloria", "Gratia", "Gravis",
    "Habitus", "Honor", "Hora", "Ignis", "Imago",
    "Imperium", "Inceptum", "Infinitus", "Ingenium",
    "Initium", "Intra", "Iunctus", "Iustitia", "Labor",
    "Laurus", "Lectus", "Legio", "Liberi", "Libertas",
    "Lumen", "Lux", "Magister", "Magnus", "Manus",
    "Memoria", "Mens", "Mors", "Mundo", "Natura",
    "Nexus", "Nobilis", "Nomen", "Novus", "Nox",
    "Oculus", "Omnis", "Opus", "Orbis", "Ordo", "Os",
    "Pax", "Perpetuus", "Persona", "Petra", "Pietas",
    "Pons", "Populus", "Potentia", "Primus", "Proelium",
    "Pulcher", "Purus", "Quaero", "Quies", "Ratio",
    "Regnum", "Sanguis", "Sapientia", "Sensus", "Serenus",
    "Sermo", "Signum", "Sol", "Solus", "Sors", "Spes",
    "Spiritus", "Stella", "Summus", "Teneo", "Terra",
    "Tigris", "Trans", "Tribuo", "Tristis", "Ultimus",
    "Unitas", "Universus", "Uterque", "Valde", "Vates",
    "Veritas", "Verus", "Vester", "Via", "Victoria",
    "Vita", "Vox", "Vultus", "Zephyrus", "Bimbalas", "Nywuctuu",
    "Anyone", "Draher", "Hackimo", "Silvyr",

]

def generate_app_name() -> str:
    return " ".join(random.choices(LATIN_MOCK, k=3))

def get_app_name() -> str:
    if not (app_name := get_config_key("app_name")):
        app_name = generate_app_name()
        save_config_key("app_name", app_name)

    return app_name

def generate_random_system_version():
    os_choices = [
        ("Windows", "3.1"),
        ("Windows", "95"),
        ("Windows", "98"),
        ("Windows", "ME"),
        ("Windows", "NT 4.0"),
        ("Windows", "2000"),
        ("Windows", "XP"),
        ("Windows", "Server 2003"),
        ("Windows", "Vista"),
        ("Windows", "7"),
        ("Windows", "8"),
        ("Windows", "8.1"),
        ("Windows", "10"),
        ("Windows", "11"),
        ("Windows", "Server 2016"),
        ("Windows", "Server 2019"),
        ("Windows", "Server 2022"),
        ("macOS", "10.9 Mavericks"),
        ("macOS", "10.10 Yosemite"),
        ("macOS", "10.11 El Capitan"),
        ("macOS", "10.12 Sierra"),
        ("macOS", "10.13 High Sierra"),
        ("macOS", "10.14 Mojave"),
        ("macOS", "10.15 Catalina"),
        ("macOS", "11 Big Sur"),
        ("macOS", "12 Monterey"),
        ("macOS", "13 Ventura"),
        ("macOS", "14 Sonoma"),
        ("iOS", "12.5.7"),
        ("iOS", "13.7"),
        ("iOS", "14.8"),
        ("iOS", "15.7"),
        ("iOS", "16.6"),
        ("iOS", "17.4"),
        ("iPadOS", "16.4"),
        ("Android", "4.4 KitKat"),
        ("Android", "5.0 Lollipop"),
        ("Android", "6.0 Marshmallow"),
        ("Android", "7.0 Nougat"),
        ("Android", "8.0 Oreo"),
        ("Android", "9 Pie"),
        ("Android", "10"),
        ("Android", "11"),
        ("Android", "12"),
        ("Android", "13"),
        ("Android", "14"),
        ("Android", "15"),
        ("Android", "16"),
        ("ChromeOS", "89"),
        ("ChromeOS", "96"),
        ("ChromeOS", "100"),
        ("ChromeOS", "110"),
        ("Ubuntu", "14.04"),
        ("Ubuntu", "16.04"),
        ("Ubuntu", "18.04"),
        ("Ubuntu", "19.10"),
        ("Ubuntu", "20.04"),
        ("Ubuntu", "21.04"),
        ("Ubuntu", "21.10"),
        ("Ubuntu", "22.04"),
        ("Ubuntu", "22.10"),
        ("Ubuntu", "23.04"),
        ("Ubuntu", "23.10"),
        ("Ubuntu", "24.04"),
        ("Debian", "7 wheezy"),
        ("Debian", "8 jessie"),
        ("Debian", "9 stretch"),
        ("Debian", "10 buster"),
        ("Debian", "11 bullseye"),
        ("Debian", "12 bookworm"),
        ("Fedora", "28"),
        ("Fedora", "29"),
        ("Fedora", "30"),
        ("Fedora", "31"),
        ("Fedora", "32"),
        ("Fedora", "33"),
        ("Fedora", "34"),
        ("Fedora", "35"),
        ("Fedora", "36"),
        ("Fedora", "37"),
        ("Fedora", "38"),
        ("Fedora", "39"),
        ("CentOS", "6"),
        ("CentOS", "7"),
        ("CentOS", "8"),
        ("CentOS Stream", "8"),
        ("CentOS Stream", "9"),
        ("AlmaLinux", "8.6"),
        ("AlmaLinux", "9.1"),
        ("Rocky Linux", "8.6"),
        ("Rocky Linux", "9.0"),
        ("Arch Linux", "rolling-2021.05.01"),
        ("Arch Linux", "rolling-2022.11.01"),
        ("Manjaro", "21.0"),
        ("Manjaro", "22.0"),
        ("Linux Mint", "18 Sarah"),
        ("Linux Mint", "19 Tara"),
        ("Linux Mint", "20 Ulyana"),
        ("Linux Mint", "21 Vanessa"),
        ("elementary OS", "5 Hera"),
        ("elementary OS", "6 Odin"),
        ("Pop!_OS", "20.04"),
        ("Pop!_OS", "22.04"),
        ("openSUSE Leap", "15.0"),
        ("openSUSE Leap", "15.3"),
        ("SUSE Enterprise", "15 SP1"),
        ("FreeBSD", "11.4"),
        ("FreeBSD", "12.3"),
        ("FreeBSD", "13.0"),
        ("FreeBSD", "14.0"),
        ("OpenBSD", "6.7"),
        ("OpenBSD", "7.0"),
        ("NetBSD", "9.2"),
        ("Solaris", "10"),
        ("Solaris", "11.4"),
        ("Haiku", "R1/beta3"),
        ("BeOS", "R5"),
        ("MorphOS", "3.18"),
        ("AROS", "2019"),
        ("ReactOS", "0.4.13"),
        ("QNX", "7.0"),
        ("Tizen", "5.5"),
        ("HarmonyOS", "2.0"),
        ("KaiOS", "2.5"),
        ("Raspberry Pi OS", "9 stretch"),
        ("Raspberry Pi OS", "10 buster"),
        ("Raspberry Pi OS", "11 bullseye"),
        ("Puppy Linux", "9.5"),
        ("Alpine Linux", "3.18.0"),
        ("Gentoo", "2023.0"),
        ("Slackware", "14.2"),
        ("TV OS", "Samsung Tizen 6"),
        ("Amazon Fire OS", "7"),
        ("MS-DOS", "6.22"),
        ("AmigaOS", "3.1"),
        ("Commodore", "64 OS"),
    ]
    os_name, os_version = random.choice(os_choices)

    version = f"{os_name} {os_version}"
    return version

def run_config():
    from . import configurator

    return configurator.api_config(None)

def _read_config() -> dict:
    global _CONFIG_CACHE, _CONFIG_MTIME_NS

    try:
        stat = CONFIG_PATH.stat()
    except FileNotFoundError:
        _CONFIG_CACHE = {}
        _CONFIG_MTIME_NS = None
        return {}

    if _CONFIG_CACHE is not None and _CONFIG_MTIME_NS == stat.st_mtime_ns:
        return _CONFIG_CACHE

    try:
        _CONFIG_CACHE = json.loads(CONFIG_PATH.read_text())
    except json.decoder.JSONDecodeError:
        logging.warning("config.json is corrupted, resetting")
        _CONFIG_CACHE = {}
    _CONFIG_MTIME_NS = stat.st_mtime_ns
    return _CONFIG_CACHE

def get_config_key(key: str) -> str | bool:
    try:
        return _read_config().get(key, False)
    except FileNotFoundError:
        return False

def save_config_key(key: str, value: str) -> bool:
    global _CONFIG_CACHE, _CONFIG_MTIME_NS

    try:

        config = _read_config().copy()
    except FileNotFoundError:

        config = {}

    config[key] = value

    tmp = CONFIG_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(config, indent=4))
    os.replace(tmp, CONFIG_PATH)
    CONFIG_PATH.chmod(0o600)
    _CONFIG_CACHE = config
    _CONFIG_MTIME_NS = CONFIG_PATH.stat().st_mtime_ns
    return True

def parse_arguments() -> dict:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--no-git",
        dest="no_git",
        action="store_true",
        help="Disable git checks and updates",
    )
    arguments = parser.parse_args()
    logging.debug(arguments)
    return arguments

class InteractiveAuthRequired(Exception):
    pass
def raise_auth():
    raise InteractiveAuthRequired()

class Heroku:
    def __init__(self):
        self.omit_log = False
        self.arguments = parse_arguments()
        self.proxy = None
        self.conn = ConnectionTcpFull
        if self.arguments.no_git:
            os.environ["HEROKU_NO_GIT"] = "1"
        try:
            self.loop = asyncio.get_running_loop()

        except RuntimeError:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)

        install_task_tracking()

        self.clients = []
        self.ready = asyncio.Event()
        self._migrate_sessions()
        self._read_sessions()
        self._get_api_token()

    def _migrate_sessions(self):
        os.makedirs(SESSIONS_DIR, exist_ok=True)

        with os.scandir(BASE_DIR) as entries:
            legacy = [
                entry
                for entry in entries
                if entry.is_file()
                and entry.name.startswith("heroku-")
                and ".session" in entry.name
            ]

        for entry in legacy:
            target = os.path.join(SESSIONS_DIR, entry.name)
            if os.path.exists(target):
                continue

            try:
                shutil.move(entry.path, target)
            except OSError:
                logging.exception(
                    "Failed to migrate legacy session file %s", entry.path
                )

    def _read_sessions(self):
        self.sessions = []
        with os.scandir(SESSIONS_DIR) as entries:
            self.sessions += [
                SQLiteSession(entry.path.rsplit(".session", maxsplit=1)[0])
                for entry in entries
                if entry.is_file()
                and entry.name.startswith("heroku-")
                and entry.name.endswith(".session")
                and "-bot-" not in entry.name
            ]

    def _get_api_token(self):
        api_token_type = collections.namedtuple("api_token", ("ID", "HASH"))

        try:

            if not get_config_key("api_id"):
                api_id, api_hash = (
                    line.strip()
                    for line in (Path(BASE_DIR) / "api_token.txt")
                    .read_text()
                    .splitlines()
                )
                save_config_key("api_id", int(api_id))
                save_config_key("api_hash", api_hash)
                (Path(BASE_DIR) / "api_token.txt").unlink()
                logging.debug("Migrated api_token.txt to config.json")

            api_token = api_token_type(
                get_config_key("api_id"),
                get_config_key("api_hash"),
            )
        except FileNotFoundError:
            try:
                from . import api_token
            except ImportError:
                try:
                    api_token = api_token_type(
                        os.environ["api_id"],
                        os.environ["api_hash"],
                    )
                except KeyError:
                    api_token = None

        self.api_token = api_token

    async def _get_token(self):
        while self.api_token is None:
            run_config()
            importlib.invalidate_caches()
            self._get_api_token()

    async def save_client_session(
        self,
        client: CustomTelegramClient,
        *,
        delay_restart: bool = False,
    ):
        if hasattr(client, "tg_id"):
            telegram_id = client.tg_id
        else:
            if not (me := await client.get_me()):
                raise RuntimeError("Attempted to save non-inited session")

            telegram_id = me.id
            client._tg_id = telegram_id
            client.tg_id = telegram_id
            client.heroku_me = me
            client.heroku_me = me

        session = SQLiteSession(
            os.path.join(
                SESSIONS_DIR,
                f"heroku-{telegram_id}",
            )
        )

        session.set_dc(
            client.session.dc_id,
            client.session.server_address,
            client.session.port,
        )

        session.auth_key = client.session.auth_key

        session.save()

        if not delay_restart:
            await client.disconnect()
            restart()

        client.session = session
        client.heroku_db = database.Database(client)
        await client.heroku_db.init()

        try:
            db = client.heroku_db
            existing = db.get("heroku.inline", "custom_bot", False)
        except Exception:
            existing = False

        if delay_restart:
            await client.disconnect()
            await asyncio.sleep(3600)

    async def _initial_setup(self) -> bool:
        if get_config_key("owner_id"):
            # owner already bound, but session lost -> QR recovery via bot PM
            from .qr_recovery import send_qr_recovery

            if await send_qr_recovery(
                int(self.api_token.ID), self.api_token.HASH
            ):
                # session was saved to disk after startup scan -> rescan
                restart()
                return True

        from .qr_recovery import run_bot_setup

        if await run_bot_setup():
            # session was saved to disk after startup scan -> rescan
            restart()
            return True

        return False

    async def _init_clients(self) -> bool:
        for session in self.sessions.copy():
            try:
                client = CustomTelegramClient(
                    session,
                    self.api_token.ID,
                    self.api_token.HASH,
                    connection=self.conn,
                    proxy=self.proxy,
                    connection_retries=None,
                    device_model=get_app_name(),
                    system_version=generate_random_system_version(),
                    app_version=".".join(map(str, __version__)) + " x64",
                    lang_code="en",
                    system_lang_code="en-US",
                )
                await client.connect()
                client.phone = "None"

                me = await client.get_me()
                client._tg_id = me.id
                client.tg_id = me.id
                client.heroku_me = me

                temp_db = database.Database(client)
                await temp_db.init()

                if legacy_token := temp_db.get("heroku.inline", "bot_token", False):
                    if not get_config_key("bot_token"):
                        save_config_key("bot_token", legacy_token)

                    temp_db.set("heroku.inline", "bot_token", None)

                self.clients += [client]
            except sqlite3.OperationalError:
                logging.error(
                    "Check that this is the only instance running. "
                    "If that doesn't help, delete the file '%s'",
                    session.filename,
                )
                continue
            except (TypeError, AuthKeyDuplicatedError):
                Path(session.filename).unlink(missing_ok=True)
                self.sessions.remove(session)
            except (ValueError, ApiIdInvalidError):

                run_config()
                return False
            except (AuthKeyUnregisteredError, InteractiveAuthRequired):
                logging.error(
                    "Session %s was terminated and re-auth is required",
                    session.filename,
                )
                from .qr_recovery import send_qr_recovery

                if await send_qr_recovery(
                    int(self.api_token.ID), self.api_token.HASH
                ):
                    from ._internal import restart

                    restart()
                self.sessions.remove(session)

        return bool(self.sessions)

    async def amain_wrapper(self, client: CustomTelegramClient):
        async with client:
            first = True
            me = await client.get_me()
            client._tg_id = me.id
            client.tg_id = me.id
            client.heroku_me = me
            client.heroku_me = me
            set_client_id(me.id)

            while await self.amain(first, client):
                first = False

    async def _badge(self, client: CustomTelegramClient):
        try:
            if os.environ.get("HEROKU_NO_GIT") == "1":
                build = "unknown"
                upd = "Git disabled"
            else:
                import git

                with git.Repo() as repo:
                    build = repo.head.commit.hexsha
                    diff = repo.git.log([f"HEAD..origin/{version.branch}", "--oneline"])
                upd = "Update required" if diff else "Up-to-date"
            pref = client.heroku_db.get("heroku.main", "command_prefix", None)

            logo = (
                "                          _           \n"
                r"  /\  /\ ___  _ __  ___  | | __ _   _ "
                "\n"
                r" / /_/ // _ \| '__|/ _ \ | |/ /| | | |"
                "\n"
                "/ __  /|  __/| |  | (_) ||   < | |_| |\n"
                r"\/ /_/  \___||_|   \___/ |_|\_\ \__,_|"
                "\n\n"
                f"• Build: {build[:7]}\n"
                f"• Version: {'.'.join(list(map(str, list(__version__))))}\n"
                f"• {upd}\n"
            )
            if not self.omit_log:
                print(logo)
                logging.debug(
                    "\n Heroku %s #%s (%s) started",
                    ".".join(list(map(str, list(__version__)))),
                    build[:7],
                    upd,
                )
                self.omit_log = True

            try:
                handler = logging.getLogger().handlers[0]
                message_thread_id = await handler.get_logs_topic_id()
                log_chat_id = handler.mod.logchat

                await client.heroku_inline.bot.send_photo(
                    log_chat_id,
                    utils.get_asset_path("HerokuStarted.png"),
                    caption=(
                        "{} <b>{} started!</b>\n\n <b>GitHub commit SHA: <a"
                        ' href="https://github.com/i-execute/Heroku/commit/{}">{}</a></b>\n'
                        " <b>Update status: {}</b>\n <b>Prefix:</b> <code>{}</code>"
                    ).format(
                        (
                            utils.get_platform_emoji()
                            if client.heroku_me.premium is True
                            else " Heroku"
                        ),
                        ".".join(list(map(str, list(__version__)))),
                        build,
                        build[:7],
                        upd,
                        "." if pref is None else pref,
                    ),
                    message_thread_id=message_thread_id,
                )
            except Exception as badge_error:
                logging.debug(f"Failed to send badge photo: {badge_error}")
            logging.debug(
                "· Started for %s · Prefix: «%s» ·",
                client.tg_id,
                client.heroku_db.get(__name__, "command_prefix", False) or ".",
            )
        except Exception:
            logging.exception("Badge error")

    async def _add_dispatcher(
        self,
        client: CustomTelegramClient,
        modules: loader.Modules,
        db: database.Database,
    ):
        dispatcher = CommandDispatcher(modules, client, db)
        client.dispatcher = dispatcher
        modules.check_security = dispatcher.check_security

        client.add_event_handler(
            dispatcher.handle_incoming,
            events.NewMessage,
        )

        client.add_event_handler(
            dispatcher.handle_incoming,
            events.ChatAction,
        )

        client.add_event_handler(
            dispatcher.handle_command,
            events.NewMessage(forwards=False),
        )

        client.add_event_handler(
            dispatcher.handle_command,
            events.MessageEdited(),
        )

        client.add_event_handler(
            dispatcher.handle_raw,
            events.Raw(),
        )

    async def amain(self, first: bool, client: CustomTelegramClient):
        client.parse_mode = "HTML"
        await client.start()

        db = database.Database(client)
        client.heroku_db = db
        await db.init()
        logging.debug("Got DB")
        logging.debug("Loading logging config...")

        modules = loader.Modules(client, db)
        client.loader = modules

        await self._add_dispatcher(client, modules, db)

        await modules.register_all(None)
        modules.send_config()
        await modules.inline.register_manager()
        await db.ensure_content_channel()
        await modules.send_ready()

        if first:
            await self._badge(client)

        await client.run_until_disconnected()

    @staticmethod
    def _loop_exception_handler(_, context: dict):
        culprit = (
            context.get("task") or context.get("future") or context.get("handle")
        )
        details = f" [{culprit!r}]" if culprit is not None else ""
        source = context.get("source_traceback")

        if source:
            details += "\nTask was created at:\n" + "".join(
                traceback.format_list(source[-5:])
            ).rstrip()

        owner = None

        if hasattr(culprit, "get_context"):
            with contextlib.suppress(Exception):
                owner = culprit.get_context().get(client_id_ctx)

        with client_id_override(owner):
            logging.error(
                "Exception on event loop! %s%s",
                context.get("message", "unknown error"),
                details,
                exc_info=context.get("exception"),
            )

    async def _main(self):
        await self._get_token()

        if (
            not self.clients and not self.sessions or not await self._init_clients()
        ) and not await self._initial_setup():
            return

        self.loop.set_exception_handler(self._loop_exception_handler)
        await asyncio.gather(
            *[self.amain_wrapper(client) for client in self.clients]
        )

    async def _shutdown_handler(self):
        for client in self.clients:
            inline = getattr(client.loader, "inline", None)
            if inline:
                for t in (inline._task, inline._cleaner_task):
                    if t:
                        t.cancel()
                try:
                    await inline._dp.stop_polling()
                    await inline.bot.session.close()
                except Exception:
                    pass
        for c in self.clients:
            await c.disconnect()
        for task in asyncio.all_tasks():
            if task is not asyncio.current_task():
                task.cancel()
        self.loop.stop()

    def main(self):
        if sys.platform != "win32":
            try:
                self.loop.add_signal_handler(
                    signal.SIGINT, lambda: asyncio.create_task(self._shutdown_handler())
                )
            except NotImplementedError:
                logging.warning("Signal handlers not supported on this platform.")
        else:
            logging.info("Running on Windows — skipping signal handler.")

        try:
            self.loop.run_until_complete(self._main())
        except KeyboardInterrupt:
            logging.info("KeyboardInterrupt received.")
            self.loop.run_until_complete(self._shutdown_handler())
        except Exception as e:
            logging.exception("Unexpected exception in main loop: %s", e)
        finally:
            logging.info("Bye!")
            try:
                self.loop.run_until_complete(self._shutdown_handler())
            except Exception:
                pass

heroku = Heroku()
