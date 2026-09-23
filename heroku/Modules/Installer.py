# CopyLeft 2026 github.com/i-execute // i_execute.t.me
# Licensed under AGPLv3.

__version__ = (2, 1, 3)
# meta developer: Execute_forge.t.me
# meta banner: https://raw.githubusercontent.com/i-execute/Modules/main/Storage/Info/MetaBanner.jpeg

# (c) Dan Gazizullin, 2021-2023. This file is part of the Hikka Userbot: github.com/hikariatama/Hikka

"""Loads and registers modules"""

from pathlib import Path
import ast
import asyncio
import contextlib
import difflib
import inspect
import io
import logging
import os
import re
import requests
import subprocess
import uuid
from importlib.machinery import ModuleSpec

from telethon.tl.custom import Message
from telethon.errors.rpcerrorlist import MediaCaptionTooLongError

from .. import loader, main, utils
from ..inline.types import InlineCall
from ..types import CoreOverwriteError, CoreUnloadError

logger = logging.getLogger(__name__)

class ModuleInstallError(RuntimeError):
    """Raised when an external module install fails after download."""

@loader.tds
class Installer(loader.Module):
    """Loads modules"""

    strings = {
        "name": "Installer",
        "link": "<b>File of</b> {class_name}\n\n<b>{prefix}lm in reply to this message to install</b>\n\n<code>{prefix}dlm {url}</code>\n\n{not_exact}",
        "file": "<b>File of</b> {class_name}\n\n<b>{prefix}lm in reply to this message to install</b>\n\n{not_exact}",
        "loading_module_via_file": "Loading the module.",
        "ml_load_module": "I'm downloading the module as a file.",
        "no_ml": "<b>Module</b> <code>{}</code> <b>cannot be exported as a file</b>",
        "not_exact": "<i>No exact match has been found, so the closest result is shown instead</i>",
        "args": "<b>You must specify arguments</b>",
        "provide_module": "<b>Provide a module to load</b>",
        "bad_unicode": "<b>Invalid Unicode formatting in module</b>",
        "load_failed": "<b>Loading failed. See logs for details</b>",
        "loaded": "<b>Module</b> <code>{}</code> <b>loaded</b>{}{}{}{}{}",
        "no_class": "<b>What class needs to be unloaded?</b>",
        "unloaded": "{} <b>Module {} unloaded.</b>",
        "unload_suggestions": "<b>Module</b> <code>{}</code> <b>not found.</b>\n\n<b>Maybe you meant:</b>",
        "modules_unloaded": "<b>Unloaded {unloaded_num} modules:</b>\n<blockquote expandable>{unloaded}</blockquote>",
        "not_unloaded": "<b>Module not unloaded.</b>",
        "modules_not_unloaded": "<b>Failed to unload {not_unloaded} modules.</b>\n<blockquote expandable>{errors}</blockquote>",
        "requirements_failed": "<b>Requirements installation failed</b>",
        "undoc": "No docs",
        "ihandler": "<code>{}</code> {}",
        "inline_init_failed": "<b>This module requires Heroku inline feature and initialization of InlineManager failed</b>\n<i>Please, remove one of your old bots from @BotFather and restart userbot to load this module</i>",
        "version_incompatible": "<b>This module requires Heroku {}+\nPlease, update with</b> <code>.update</code>",
        "ffmpeg_required": "<b>This module requires FFMPEG, which is not installed</b>",
        "developer": "<b>Developer:</b> {}",
        "depends_from": "<b>Dependencies:</b> \n{}",
        "by": "by",
        "cancel": "Cancel",
        "unload_core": "<b>You can't unload core module</b> <code>{}</code><b></b>\n\n<i> Don't report it as bug. It's a security measure to prevent replacing core modules with some junk</i>",
        "cannot_unload_lib": "<b>You can't unload library</b>",
        "_cls_doc": "Loads modules",
        "404": "<b>Module not found</b>",
        "_cmd_doc_ml": "<module> - Send module as a file",
        "result": "<b>Search result for</b> <code>{query}</code>\n\n<b>{name}</b> by <b>{dev}</b>\n<i>{cls_doc}</i>\n<b>Commands:</b>\n{commands}\n\n<code>{prefix}dlm {mhash}</code>",
        "installing": "<b>Downloading module</b> <code>{}</code>...",
        "no_module": "<b>Can't download module from this link.</b>",
        "_cmd_doc_dlm": "<file/URL> - Load a module",
        "_cmd_doc_lm": "<reply to file> - Load a module from file",
        "_cmd_doc_ulm": "<module> - Unload a module",
        "confirm_nuke": "<b>This will fully remove the userbot: stop service, delete systemd unit and ~/Heroku.</b>",
        "nuke": " Nuke it",
        "nuking": "<b>Nuking...</b>",
        "dlmall_no_repo": "<b>Set the modules repo first:</b> <code>.cfg Installer.modules_repo &lt;url&gt;</code>",
        "dlmall_start": "<b>Installing all modules from</b> <code>{}</code>",
        "dlmall_failed": "<b>Installed {} of {} modules.</b>\nFailed:\n<blockquote expandable>{}</blockquote>",
        "dlmall_done": "<b>Installed {} modules.</b>",
        "overwrite_module": "<b>This module attempted to override the core one (</b><code>{}</code><b>)</b>\n\n<i> Don't report it as bug. It's a security measure to prevent replacing core modules with some junk</i>",
        "overwrite_command": "<b>This module attempted to override the core command (</b><code>{}{}</code><b>)</b>\n\n<i> Don't report it as bug. It's a security measure to prevent replacing core modules' commands with some junk</i>",
    }

    def __init__(self):
        self.fully_loaded = False

        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "modules_repo",
                "",
                lambda: "Base URL of modules repo (with full.txt)",
            ),
            loader.ConfigValue(
                "command_emoji",
                "",
                lambda: "Emoji for command",
            ),
        )

    async def client_ready(self):
        while not (settings := self.lookup("settings")):
            await asyncio.sleep(0.5)

        self.allmodules.add_aliases(settings.get("aliases", {}))

        main.heroku.ready.set()

        asyncio.ensure_future(self._update_modules())

    @loader.loop(interval=3, wait_before=True, autostart=True)
    async def _config_autosaver(self):
        for mod in self.allmodules.modules:
            if (
                not hasattr(mod, "config")
                or not mod.config
                or not isinstance(mod.config, loader.ModuleConfig)
            ):
                continue

            for option, config in mod.config._config.items():
                if not hasattr(config, "_save_marker"):
                    continue

                delattr(mod.config._config[option], "_save_marker")
                mod.pointer("__config__", {})[option] = config.value

        for lib in self.allmodules.libraries:
            if (
                not hasattr(lib, "config")
                or not lib.config
                or not isinstance(lib.config, loader.ModuleConfig)
            ):
                continue

            for option, config in lib.config._config.items():
                if not hasattr(config, "_save_marker"):
                    continue

                delattr(lib.config._config[option], "_save_marker")
                lib._lib_pointer("__config__", {})[option] = config.value

        self._db.save()

    @loader.command()
    async def dlm(self, message: Message):
        args = utils.get_args_raw(message)

        if not args:
            repo = utils.normalize_git_url(self.config["modules_repo"])
            if not repo or not utils.check_url(repo):
                await utils.answer(message, self.strings["dlmall_no_repo"])
                return

            await utils.answer(
                message, self.strings["dlmall_start"].format(repo)
            )

            try:
                r = await utils.run_sync(
                    requests.get, f"{repo.rstrip('/')}/full.txt", timeout=30
                )
                r.raise_for_status()
                links = [l.strip() for l in r.text.strip().splitlines() if l.strip()]
            except Exception as e:
                logger.warning("Failed to fetch full.txt from %s: %s", repo, e)
                await utils.answer(message, self.strings["no_module"])
                return

            if not links:
                await utils.answer(message, self.strings["no_module"])
                return

            failed = []
            for link in links:
                url = (
                    utils.normalize_git_url(link)
                    if utils.check_url(link)
                    else f"{repo.rstrip('/')}/{link}.py"
                )
                try:
                    r = await utils.run_sync(requests.get, url, timeout=30)
                    r.raise_for_status()
                    if not await self.load_module(
                        r.text, message, origin=url, save_fs=True
                    ):
                        failed.append(link.split("/")[-1])
                except Exception as e:
                    logger.warning("dlmall: failed %s: %s", url, e)
                    failed.append(link.split("/")[-1])

            installed = len(links) - len(failed)
            if installed == 0:
                await utils.answer(message, self.strings["no_module"])
            elif failed:
                await utils.answer(
                    message,
                    self.strings["dlmall_failed"].format(
                        installed,
                        len(links),
                        "\n".join(failed),
                    ),
                )
            else:
                await utils.answer(
                    message, self.strings["dlmall_done"].format(installed)
                )
            return

        args = utils.normalize_git_url(args)
        if not utils.check_url(args):
            await utils.answer(message, self.strings["no_module"])
            return

        await utils.answer(message, self.strings["installing"].format(args))

        try:
            r = await utils.run_sync(
                requests.get, args, timeout=30, allow_redirects=False
            )
            r.raise_for_status()
            doc = r.text
        except Exception as e:
            logger.warning("Failed to download module from %s: %s", args, e)
            await utils.answer(message, self.strings["no_module"])
            return

        await self.load_module(doc, message, origin="<string>", save_fs=True)

    @loader.command()
    async def lm(self, message: Message):
        msg = message if message.file else (await message.get_reply_message())

        if msg is None or msg.media is None:
            await utils.answer(message, self.strings["provide_module"])
            return

        await utils.answer(message, self.strings["loading_module_via_file"])

        doc = await msg.download_media(bytes)

        try:
            doc = doc.decode()
        except UnicodeDecodeError:
            await utils.answer(message, self.strings["bad_unicode"])
            return

        await self.load_module(doc, message, save_fs=True)


    async def load_module(
        self,
        doc: str,
        message: Message,
        name: str | None = None,
        origin: str = "<string>",
        did_requirements: bool = False,
        save_fs: bool = True,
        _raise_install_errors: bool = False,
    ) -> bool:
        module_label = name or origin

        if any(
            line.replace(" ", "") == "#scope:ffmpeg" for line in doc.splitlines()
        ) and os.system("ffmpeg -version 1>/dev/null 2>/dev/null"):
            logger.error(
                "Module %s requires ffmpeg, but ffmpeg is not installed",
                module_label,
            )
            if isinstance(message, Message):
                await utils.answer(message, self.strings["ffmpeg_required"])
            return False

        if (
            any(line.replace(" ", "") == "#scope:inline" for line in doc.splitlines())
            and not self.inline.init_complete
        ):
            logger.error(
                "Module %s requires inline mode, but inline initialization failed",
                module_label,
            )
            if isinstance(message, Message):
                await utils.answer(message, self.strings["inline_init_failed"])
            return False

        if re.search(r"# ?scope: ?heroku_min", doc):
            ver = re.search(r"# ?scope: ?heroku_min ((?:\d+\.){2}\d+)", doc).group(1)
            ver_ = tuple(map(int, ver.split(".")))
            if main.__version__ < ver_:
                logger.error(
                    "Module %s requires Heroku %s, current version is %s",
                    module_label,
                    ver,
                    ".".join(map(str, main.__version__)),
                )
                if isinstance(message, Message):
                    await utils.answer(
                        message, self.strings["version_incompatible"].format(ver)
                    )
                return False

        developer = re.search(r"# ?meta developer: ?(.+)", doc)
        developer = developer.group(1) if developer else False


        if name is None:
            try:
                node = ast.parse(doc)
                uid = next(
                    n.name
                    for n in node.body
                    if isinstance(n, ast.ClassDef)
                    and any(
                        isinstance(base, (ast.Attribute, ast.Name))
                        and ast.unparse(base).split(".")[-1] == "Module"
                        for base in n.bases
                    )
                )
            except Exception:
                uid = "__extmod_" + str(uuid.uuid4())
        else:

            uid = name.replace("%", "%%").replace(".", "%d")

        module_name = f"heroku.Modules.{uid}"

        async def core_overwrite(e: CoreOverwriteError):
            nonlocal message

            with contextlib.suppress(Exception):
                self.allmodules.modules.remove(instance)

            if not message:
                return

            await utils.answer(
                message,
                self.strings[f"overwrite_{e.type}"].format(
                    *(
                        (e.target,)
                        if e.type == "module"
                        else (utils.escape_html(self.get_prefix()), e.target)
                    )
                ),
            )

        try:
            try:
                spec = ModuleSpec(
                    module_name,
                    loader.StringLoader(doc, f"<external {module_name}>"),
                    origin=f"<external {module_name}>",
                )
                instance = await self.allmodules.register_module(
                    spec,
                    module_name,
                    origin,
                    save_fs=save_fs,
                )
            except ImportError as e:
                logger.error(
                    "Module %s failed to load, missing dependency: %s",
                    module_label,
                    getattr(e, "name", e),
                )
                if message is not None:
                    await utils.answer(message, self.strings["requirements_failed"])

                return False
            except CoreOverwriteError as e:
                logger.error(
                    "Module %s tried to overwrite core %s %s",
                    module_label,
                    e.type,
                    e.target,
                )
                await core_overwrite(e)
                return False
            except loader.LoadError as e:
                logger.error("Module %s failed security checks: %s", module_label, e)
                with contextlib.suppress(Exception):
                    await self.allmodules.unload_module(instance.__class__.__name__)

                with contextlib.suppress(Exception):
                    self.allmodules.modules.remove(instance)

                if message:
                    if isinstance(e, loader.LoadError):
                        await utils.answer(
                            message,
                            (
                                ""
                                f" <b>{utils.escape_html(str(e))}</b>"
                            ),
                        )
                return False
        except Exception as e:
            logger.exception("Loading external module failed due to %s", e)

            if message is not None:
                await utils.answer(message, self.strings["load_failed"])

            return False

        if hasattr(instance, "__version__") and isinstance(instance.__version__, tuple):
            version = (
                "<b><i>"
                f" (v{'.'.join(list(map(str, list(instance.__version__))))})</i></b>"
            )
        else:
            version = ""

        try:
            try:
                self.allmodules.send_config_one(instance)

                await self.allmodules.send_ready_one(
                    instance,
                    no_self_unload=True,
                    from_dlmod=bool(message),
                )
            except CoreOverwriteError as e:
                logger.error(
                    "Module %s tried to overwrite core %s %s during ready stage",
                    module_label,
                    e.type,
                    e.target,
                )
                await core_overwrite(e)
                return False
            except loader.LoadError as e:
                logger.error(
                    "Module %s failed during ready security checks: %s",
                    module_label,
                    e,
                )
                with contextlib.suppress(Exception):
                    await self.allmodules.unload_module(instance.__class__.__name__)

                with contextlib.suppress(Exception):
                    self.allmodules.modules.remove(instance)

                if message:
                    if isinstance(e, loader.LoadError):
                        await utils.answer(
                            message,
                            (
                                ""
                                f" <b>{utils.escape_html(str(e))}</b>"
                            ),
                        )
                return False
            except loader.SelfUnload as e:
                logger.warning(
                    "Module %s unloaded itself during installation: %s",
                    module_label,
                    e,
                )
                with contextlib.suppress(Exception):
                    await self.allmodules.unload_module(instance.__class__.__name__)

                with contextlib.suppress(Exception):
                    self.allmodules.modules.remove(instance)

                if message:
                    await utils.answer(
                        message,
                        (
                            ""
                            f" <b>{utils.escape_html(str(e))}</b>"
                        ),
                    )
                return False
            except loader.SelfSuspend as e:
                logger.warning(
                    "Module %s suspended itself during installation: %s",
                    module_label,
                    e,
                )
                if message:
                    await utils.answer(
                        message,
                        (
                            " <b>Module suspended itself\nReason:"
                            f" {utils.escape_html(str(e))}</b>"
                        ),
                    )
                return False
        except Exception as e:
            logger.exception("Module threw because of %s", e)

            if message is not None:
                await utils.answer(message, self.strings["load_failed"])

            return False

        instance.heroku_meta_pic = next(
            (
                line.replace(" ", "").split("#metapic:", maxsplit=1)[1]
                for line in doc.splitlines()
                if line.replace(" ", "").startswith("#metapic:")
            ),
            None,
        )

        for alias, cmd in self.lookup("settings").get("aliases", {}).items():
            _cmd = cmd.split(maxsplit=1)
            if _cmd[0] in instance.commands:
                self.allmodules.add_alias(alias, *_cmd)

        try:
            modname = instance.strings("name")
        except (KeyError, AttributeError):
            modname = getattr(instance, "name", instance.__class__.__name__)

        if message is None:
            return True

        modhelp = []
        mod_doc = ""

        if instance.__doc__:
            mod_doc += (
                "<i>\n"
                f" {utils.escape_html(inspect.getdoc(instance))}</i>\n\n"
            )


        depends_from = []
        for key in dir(instance):
            value = getattr(instance, key)
            if isinstance(value, loader.Library):
                depends_from.append(
                    ""
                    " <code>{}</code> <b>{}</b> <code>{}</code>".format(
                        value.__class__.__name__,
                        self.strings["by"],
                        (
                            value.developer
                            if isinstance(getattr(value, "developer", None), str)
                            else "Unknown"
                        ),
                    )
                )
        placeholders = utils.help_placeholders(
            getattr(getattr(instance, "__class__"), "__name__"), self
        )

        depends_from = (
            self.strings["depends_from"].format("\n".join(depends_from))
            if depends_from
            else ""
        )

        def loaded_msg():
            nonlocal modname, version, mod_doc, modhelp, placeholders, developer, origin, depends_from
            return self.strings["loaded"].format(
                modname.strip(),
                mod_doc if mod_doc else "",
                "<blockquote expandable>{}</blockquote>".format("\n".join(modhelp)),
                "\n<blockquote expandable>{}</blockquote>".format(
                    "\n".join(placeholders)
                ),
                developer,
                depends_from,
            )

        if developer:
            developer = self.strings["developer"].format(utils.escape_html(developer))
        else:
            developer = ""

        if any(
            line.replace(" ", "") == "#scope:disable_onload_docs"
            for line in doc.splitlines()
        ):
            await utils.answer(message, loaded_msg())
            return True

        for _name, fun in sorted(
            instance.commands.items(),
            key=lambda x: x[0],
        ):
            modhelp.append(
                "{} <code>{}{}</code> {}".format(
                    f"{self.config['command_emoji']}",
                    utils.escape_html(self.get_prefix()),
                    _name,
                    (
                        utils.escape_html(inspect.getdoc(fun))
                        if fun.__doc__
                        else self.strings["undoc"]
                    ),
                )
            )

        if self.inline.init_complete:
            for _name, fun in sorted(
                instance.inline_handlers.items(),
                key=lambda x: x[0],
            ):
                modhelp.append(
                    self.strings["ihandler"].format(
                        f"@{self.inline.bot_username} {_name}",
                        (
                            utils.escape_html(inspect.getdoc(fun))
                            if fun.__doc__
                            else self.strings["undoc"]
                        ),
                    )
                )

        try:
            await utils.answer(message, loaded_msg())
        except MediaCaptionTooLongError:
            if hasattr(message, "reply"):
                await message.reply(loaded_msg())
            else:
                await message.edit(loaded_msg())

        return True

    @loader.command()
    async def ulm(self, message: Message):
        if not (raw_args := utils.get_args_raw(message)):
            await utils.answer(message, self.strings["no_class"])
            return

        args = raw_args
        force = False
        first_line = args.split("\n", 1)[0].strip()
        if first_line == "-f":
            force = True
            rest = args.split("\n", 1)
            args = rest[1].strip() if len(rest) > 1 else ""
        elif args.startswith("-f "):
            force = True
            args = args[3:].strip()

        if not args:
            await utils.answer(message, self.strings["no_class"])
            return

        raw_list = re.split(r"[,\n]", args)
        modules = [m.strip() for m in raw_list if m.strip()]

        if len(modules) == 1:
            if not self.lookup(modules[0]):
                suggestions = self._get_unload_suggestions(modules[0])
                if suggestions:
                    await self.inline.form(
                        self.strings["unload_suggestions"].format(
                            utils.escape_html(modules[0])
                        ),
                        message=message,
                        reply_markup=[
                            [
                                {
                                    "text": label,
                                    "callback": self._inline__unload_suggested, "style": "primary",
                                    "args": (classname, force),
                                }
                            ]
                            for classname, label in suggestions
                        ]
                        + [
                            [
                                {
                                    "text": self.strings["cancel"].replace("", ""),
                                    "action": "close", "style": "primary",
                                }
                            ]
                        ],
                        silent=True,
                    )
                    return

            msg = await self.unload_module(modules[0], force=force)
        else:
            success = []
            errors = []
            msg = ""
            for module in modules:
                status = await self.unload_module(module)
                if "" in status or "" in status or "" in status:
                    if "" in status:
                        status = status.split("<code>")[0]

                    errors.append(f"<code>{module}</code> — {status}")
                else:
                    success.append(f"<code>{module}</code>")

            if success:
                msg += self.strings["modules_unloaded"].format(
                    unloaded_num=len(success), unloaded=", ".join(success)
                )
            if errors:
                msg += "\n" + self.strings["modules_not_unloaded"].format(
                    not_unloaded=len(errors),
                    errors="\n".join(errors),
                )

        await utils.answer(message, msg)

    def _get_unload_suggestions(
        self,
        query: str,
        limit: int = 3,
    ) -> list[tuple[str, str]]:
        query = query.lower()
        scored = []

        for module in self.allmodules.modules:
            if self._is_core_module(module):
                continue

            classname = module.__class__.__name__
            public_name = str(getattr(module, "name", "") or module.strings["name"])
            names = {
                classname,
                classname[:-3] if classname.endswith("Mod") else classname,
                public_name,
            }
            score = max(
                difflib.SequenceMatcher(None, query, name.lower()).ratio()
                for name in names
                if name
            )
            label = public_name
            scored.append((score, classname.lower(), classname, label))

        return [
            (classname, label)
            for _, _, classname, label in sorted(scored, reverse=True)[:limit]
        ]

    def _is_core_module(self, module) -> bool:
        module_name = getattr(module.__class__, "__module__", "")
        if not module_name.startswith("heroku.Modules."):
            return False

        module_file = module_name.rsplit(".", 1)[-1]
        return os.path.isfile(
            os.path.join(utils.get_base_dir(), "Modules", f"{module_file}.py")
        )

    async def _inline__unload_suggested(
        self,
        call: InlineCall,
        module: str,
        force: bool = False,
    ):
        await call.edit(await self.unload_module(module, force=force))

    async def unload_module(self, module: str, force: bool = False) -> str:
        instance = self.lookup(module)

        if instance and self._is_core_module(instance):
            return self.strings["unload_core"].format(module)

        if instance and issubclass(instance.__class__, loader.Library):
            return self.strings["cannot_unload_lib"]

        try:
            worked = await self.allmodules.unload_module(module)
        except CoreUnloadError:
            return self.strings["unload_core"].format(module)

        msg = (
            self.strings["unloaded"].format(
                "",
                ", ".join(
                    [(mod[:-3] if mod.endswith("Mod") else mod) for mod in worked]
                ),
            )
            if worked
            else self.strings["not_unloaded"]
        )
        for mod_name in worked:
            utils.unregister_placeholders(mod_name)

        if force and worked:
            try:
                for key in list(self._db.keys()):
                    if not isinstance(key, str):
                        continue
                    low = key.lower()
                    for mod_name in worked:
                        base = mod_name[:-3] if mod_name.endswith("Mod") else mod_name
                        candidates = {mod_name.lower(), base.lower()}
                        if any(
                            low == c
                            or low.startswith(c + ".")
                            or low.startswith(c + "_")
                            or c in low
                            for c in candidates
                        ):
                            try:
                                del self._db[key]
                            except Exception:
                                pass

                try:
                    self._db.save()
                except Exception:
                    logger.debug(
                        "Failed to save DB after force-unload cleanup", exc_info=True
                    )
            except Exception:
                logger.exception("Failed to cleanup DB for force unload")

        return msg

    @loader.command()
    async def nuke(self, message: Message):
        """Fully remove the userbot: stop service, delete systemd unit and ~/Heroku"""
        await self.inline.form(
            self.strings["confirm_nuke"],
            message,
            reply_markup=[
                {
                    "text": self.strings["nuke"],
                    "callback": self._inline__nuke, "style": "primary",
                },
                {
                    "text": self.strings["cancel"],
                    "action": "close",
                    "style": "primary",
                },
            ],
        )

    async def _inline__nuke(self, call: InlineCall):
        await utils.answer(call, self.strings["nuking"])
        await asyncio.sleep(1)
        subprocess.Popen(
            ["bash", str(Path(__file__).resolve().parent.parent.parent / "Storage" / "Nuke.sh")],
            start_new_session=True,
        )

    async def _update_modules(self):
        self._secure_boot = False

        if self._db.get(loader.__name__, "secure_boot", False):
            self._db.set(loader.__name__, "secure_boot", False)
            self._secure_boot = True
        else:
            aliases = {
                alias: cmd
                for alias, cmd in self.lookup("settings").get("aliases", {}).items()
                if self.allmodules.add_alias(alias, *cmd.split(maxsplit=1))
            }

            self.lookup("settings").set("aliases", aliases)

        self.fully_loaded = True

        with contextlib.suppress(AttributeError):
            await self.lookup("Updater").full_restart_complete(self._secure_boot)

    async def reload_core(self) -> int:
        """Forcefully reload all core modules"""
        self.fully_loaded = False

        if self._secure_boot:
            self._db.set(loader.__name__, "secure_boot", True)

        if not self._db.get(main.__name__, "remove_core_protection", False):
            for module in self.allmodules.modules:
                if module.__origin__.startswith("<core"):
                    module.__origin__ = "<reload-core>"

        loaded = await self.allmodules.register_all(no_external=True)
        for instance in loaded:
            self.allmodules.send_config_one(instance)
            await self.allmodules.send_ready_one(
                instance,
                no_self_unload=False,
                from_dlmod=False,
            )

        self.fully_loaded = True
        return len(loaded)

    @loader.command()
    async def ml(self, message: Message):
        """| send module via file"""
        if not (args := utils.get_args_raw(message)):
            await utils.answer(message, self.strings["args"])
            return

        await utils.answer(message, self.strings["ml_load_module"])

        exact = True
        if not (
            class_name := next(
                (
                    module.strings("name")
                    for module in self.allmodules.modules
                    if args.lower()
                    in {
                        module.strings("name").lower(),
                        module.__class__.__name__.lower(),
                    }
                ),
                None,
            )
        ):
            if not (
                class_name := next(
                    reversed(
                        sorted(
                            [
                                module.strings["name"].lower()
                                for module in self.allmodules.modules
                            ]
                            + [
                                module.__class__.__name__.lower()
                                for module in self.allmodules.modules
                            ],
                            key=lambda x: difflib.SequenceMatcher(
                                None,
                                args.lower(),
                                x,
                            ).ratio(),
                        )
                    ),
                    None,
                )
            ):
                await utils.answer(message, self.strings["404"])
                return

            exact = False

        try:
            module = self.lookup(class_name)
            sys_module = inspect.getmodule(module)
        except Exception:
            await utils.answer(message, self.strings["404"])
            return

        module_data = sys_module.__loader__.data
        if isinstance(module_data, str):
            module_data = module_data.encode("utf-8")

        module_doc = (
            module_data.decode("utf-8", errors="ignore")
            if isinstance(module_data, (bytes, bytearray))
            else str(module_data)
        )

        if any(
            line.replace(" ", "") == "#scope:no_ml" for line in module_doc.splitlines()
        ):
            await utils.answer(
                message,
                self.strings["no_ml"].format(utils.escape_html(class_name)),
            )
            return

        link = module.__origin__

        text = (
            f"<b> {utils.escape_html(class_name)}</b>"
            if not utils.check_url(link)
            else (
                f' <b><a href="{link}">Link</a> for'
                f" {utils.escape_html(class_name)}:</b>"
                f' <code>{link}</code>\n\n{self.strings["not_exact"] if not exact else ""}'
            )
        )

        text = (
            self.strings["link"].format(
                class_name=utils.escape_html(class_name),
                url=link,
                not_exact=self.strings["not_exact"] if not exact else "",
                prefix=utils.escape_html(self.get_prefix()),
            )
            if utils.check_url(link)
            else self.strings["file"].format(
                class_name=utils.escape_html(class_name),
                not_exact=self.strings["not_exact"] if not exact else "",
                prefix=utils.escape_html(self.get_prefix()),
            )
        )

        file = io.BytesIO(module_data)
        file.name = f"{class_name}.py"
        file.seek(0)

        await utils.answer(
            message,
            text,
            file=file,
            reply_to=getattr(message, "reply_to_msg_id", None),
        )

    def _format_result(
        self,
        result: dict,
        query: str,
        no_translate: bool = False,
    ) -> str:
        commands = "\n".join(
            [
                f" <code>{utils.escape_html(self.get_prefix())}{utils.escape_html(cmd)}</code>:"
                f" <b>{utils.escape_html(cmd_doc)}</b>"
                for cmd, cmd_doc in result["module"]["commands"].items()
            ]
        )

        kwargs = {
            "name": utils.escape_html(result["module"]["name"]),
            "dev": utils.escape_html(result["module"]["dev"]),
            "commands": commands,
            "cls_doc": utils.escape_html(result["module"]["cls_doc"]),
            "mhash": result["module"]["hash"],
            "query": utils.escape_html(query),
            "prefix": utils.escape_html(self.get_prefix()),
        }

        strings = (
            self.strings.get("result", "en")
            if self.config["translate"] and not no_translate
            else self.strings["result"]
        )

        text = strings.format(**kwargs)

        if len(text) > 1980:
            kwargs["commands"] = "..."
            text = strings.format(**kwargs)

        return text
