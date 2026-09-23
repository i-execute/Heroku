# CopyLeft 2026 github.com/i-execute // i_execute.t.me
# Licensed under AGPLv3.

# (c) Dan Gazizullin, 2021-2023. This file is part of the Hikka Userbot: github.com/hikariatama/Hikka

import asyncio
import builtins
import contextlib
import contextvars
import importlib
import importlib.machinery
import importlib.util
import inspect
import logging
import os
import sys
import typing
from functools import wraps
from pathlib import Path
from types import FunctionType
from uuid import uuid4

from telethon.tl.tlobject import TLObject

import heroku._herokutl_compat  # noqa: F401  installs herokutl->telethon alias

from . import main, security, utils, validators
from ._internal import resolve_client_id, set_client_id, tag_client_id
from .database import Database
from .inline.core import BotUpdateType, InlineManager
from .translations import Strings
from .types import (
    Command,
    ConfigCategory,
    ConfigValue,
    CoreOverwriteError,
    CoreUnloadError,
    InlineMessage,
    JSONSerializable,
    Library,
    LibraryConfig,
    LoadError,
    Module,
    ModuleConfig,
    SelfSuspend,
    SelfUnload,
    StopLoop,
    StringLoader,
    get_callback_handlers,
    get_commands,
    get_inline_handlers,
)

if typing.TYPE_CHECKING:
    from .tl_cache import CustomTelegramClient

__all__ = [
    "Modules",
    "InfiniteLoop",
    "Command",
    "CoreOverwriteError",
    "CoreUnloadError",
    "InlineMessage",
    "JSONSerializable",
    "Library",
    "LibraryConfig",
    "LoadError",
    "Module",
    "SelfSuspend",
    "SelfUnload",
    "StopLoop",
    "StringLoader",
    "get_commands",
    "get_inline_handlers",
    "get_callback_handlers",
    "validators",
    "Database",
    "InlineManager",
    "Strings",
    "ConfigCategory",
    "ConfigValue",
    "ModuleConfig",
    "owner",
    "group_owner",
    "group_admin_add_admins",
    "group_admin_change_info",
    "group_admin_ban_users",
    "group_admin_delete_messages",
    "group_admin_pin_messages",
    "group_admin_invite_users",
    "group_admin",
    "group_member",
    "pm",
    "unrestricted",
    "inline_everyone",
    "loop",
    "need_update",
]

logger = logging.getLogger(__name__)

owner = security.owner

sudo = security.sudo
support = security.support

group_owner = security.group_owner
group_admin_add_admins = security.group_admin_add_admins
group_admin_change_info = security.group_admin_change_info
group_admin_ban_users = security.group_admin_ban_users
group_admin_delete_messages = security.group_admin_delete_messages
group_admin_pin_messages = security.group_admin_pin_messages
group_admin_invite_users = security.group_admin_invite_users
group_admin = security.group_admin
group_member = security.group_member
pm = security.pm
unrestricted = security.unrestricted
inline_everyone = security.inline_everyone

async def stop_placeholder() -> bool:
    return True

class Placeholder:
    pass
native_import = builtins.__import__
_IMPORT_DEPTH = contextvars.ContextVar("_IMPORT_DEPTH", default=0)
_MAX_IMPORT_DEPTH = 80

def patched_import(name: str, *args, **kwargs):
    depth = _IMPORT_DEPTH.get()
    if depth > _MAX_IMPORT_DEPTH:
        return native_import(name, *args, **kwargs)
    token = _IMPORT_DEPTH.set(depth + 1)
    try:
        match name:
            case s if s.startswith("telethon"):
                return native_import("telethon" + name[8:], *args, **kwargs)

        return native_import(name, *args, **kwargs)
    finally:
        _IMPORT_DEPTH.reset(token)

builtins.__import__ = patched_import

class InfiniteLoop:
    _task = None
    status = False
    module_instance = None                        

    def __init__(
        self,
        func: FunctionType,
        interval: int,
        autostart: bool,
        wait_before: bool,
        stop_clause: str | None,
    ):
        self.func = func
        self.interval = interval
        self._wait_before = wait_before
        self._stop_clause = stop_clause
        self.autostart = autostart
        self._wait_for_stop = asyncio.Event()

    def _stop(self, *args, **kwargs):
        self._wait_for_stop.set()

    @tag_client_id("module_instance.allmodules.client.tg_id")
    def stop(self, *args, **kwargs):
        if self._task:
            logger.debug("Stopped loop for method %s", self.func)
            self._wait_for_stop = asyncio.Event()
            self.status = False
            self._task.add_done_callback(self._stop)
            self._task.cancel()
            self._task = None
            return asyncio.ensure_future(self._wait_for_stop.wait())

        logger.debug("Loop is not running")
        return asyncio.ensure_future(stop_placeholder())

    @tag_client_id("module_instance.allmodules.client.tg_id")
    def start(self, *args, **kwargs):
        if not self._task:
            logger.debug("Started loop for method %s", self.func)
            self._task = asyncio.ensure_future(self.actual_loop(*args, **kwargs))
        else:
            logger.debug("Attempted to start already running loop")

    async def actual_loop(self, *args, **kwargs):

        while not self.module_instance:
            await asyncio.sleep(0.01)

        set_client_id(
            resolve_client_id(self, "module_instance.allmodules.client.tg_id")
        )

        if isinstance(self._stop_clause, str) and self._stop_clause:
            self.module_instance.set(self._stop_clause, True)

        self.status = True

        while self.status:
            if self._wait_before:
                await asyncio.sleep(self.interval)

            if (
                isinstance(self._stop_clause, str)
                and self._stop_clause
                and not self.module_instance.get(self._stop_clause, False)
            ):
                break

            try:
                await self.func(self.module_instance, *args, **kwargs)
            except StopLoop:
                break
            except Exception:
                logger.exception("Error running loop!")

            if not self._wait_before:
                await asyncio.sleep(self.interval)

        self._wait_for_stop.set()

        self.status = False
        self._task = None

    def __del__(self):
        self.stop()

def loop(
    interval: int = 5,
    autostart: bool | None = False,
    wait_before: bool | None = False,
    stop_clause: str | None = None,
) -> FunctionType:
    def wrapped(func):
        return InfiniteLoop(func, interval, autostart, wait_before, stop_clause)

    return wrapped

MODULES_NAME = "Modules"
ru_keys = 'ёйцукенгшщзхъфывапролджэячсмитьбю.Ё"№;%:?ЙЦУКЕНГШЩЗХЪФЫВАПРОЛДЖЭ/ЯЧСМИТЬБЮ,'
en_keys = "`qwertyuiop[]asdfghjkl;'zxcvbnm,./~@#$%^&QWERTYUIOP{}ASDFGHJKL:\"|ZXCVBNM<>?"

BASE_DIR = (
    "/data"
    if "DOCKER" in os.environ
    else os.path.normpath(os.path.join(utils.get_base_dir(), ".."))
)

LOADED_MODULES_DIR = os.path.join(BASE_DIR, "LoadedModules")
LOADED_MODULES_PATH = Path(LOADED_MODULES_DIR)
LOADED_MODULES_PATH.mkdir(parents=True, exist_ok=True)

def _iter_module_files(
    directory: str | Path,
    *,
    suffix: str = ".py",
    include: typing.Callable[[str], bool] | None = None,
) -> list[str]:
    with os.scandir(directory) as entries:
        return [
            entry.path
            for entry in entries
            if entry.is_file()
            and entry.name.endswith(suffix)
            and not entry.name.startswith("_")
            and (include(entry.name) if include else True)
        ]

def translatable_docstring(cls):
    @wraps(cls.config_complete)
    def config_complete(self, *args, **kwargs):
        def proccess_decorators(mark: str, obj: str):
            nonlocal self
            for attr in dir(func_):
                if (
                    attr.endswith("_doc")
                    and attr.count("_") == 1
                    and isinstance(getattr(func_, attr), str)
                ):
                    var = f"strings_{attr.split('_')[0]}"
                    if not hasattr(self, var):
                        setattr(self, var, {})

                    getattr(self, var).setdefault(f"{mark}{obj}", getattr(func_, attr))

        for command_, func_ in get_commands(cls).items():
            proccess_decorators("_cmd_doc_", command_)
            try:
                func_.__doc__ = self.strings[f"_cmd_doc_{command_}"]
            except AttributeError:
                func_.__func__.__doc__ = self.strings[f"_cmd_doc_{command_}"]

        for inline_handler_, func_ in get_inline_handlers(cls).items():
            proccess_decorators("_ihandle_doc_", inline_handler_)
            try:
                func_.__doc__ = self.strings[f"_ihandle_doc_{inline_handler_}"]
            except AttributeError:
                func_.__func__.__doc__ = self.strings[f"_ihandle_doc_{inline_handler_}"]

        self.__doc__ = self.strings["_cls_doc"]

        return (
            self.config_complete._old_(self, *args, **kwargs)
            if not kwargs.pop("reload_dynamic_translate", None)
            else True
        )

    config_complete._old_ = cls.config_complete
    cls.config_complete = config_complete

    for command_, func in get_commands(cls).items():
        cls.strings[f"_cmd_doc_{command_}"] = inspect.getdoc(func)

    for inline_handler_, func in get_inline_handlers(cls).items():
        cls.strings[f"_ihandle_doc_{inline_handler_}"] = inspect.getdoc(func)

    cls.strings["_cls_doc"] = inspect.getdoc(cls)

    return cls

tds = translatable_docstring                                   

def ratelimit(func: Command) -> Command:
    func.ratelimit = True
    return func

def tag(*tags, **kwarg_tags):
    def inner(func: Command) -> Command:
        for _tag in tags:
            setattr(func, _tag, True)

        for _tag, value in kwarg_tags.items():
            setattr(func, _tag, value)

        return func

    return inner

def _mark_method(mark: str, *args, **kwargs) -> typing.Callable[..., Command]:
    def decorator(func: Command) -> Command:
        setattr(func, mark, True)
        for arg in args:
            setattr(func, arg, True)

        for kwarg, value in kwargs.items():
            setattr(func, kwarg, value)

        return func

    return decorator

def command(*args, **kwargs):
    return _mark_method("is_command", *args, **kwargs)

def debug_method(*args, **kwargs):
    return _mark_method("is_debug_method", *args, **kwargs)

def inline_handler(*args, **kwargs):
    return _mark_method("is_inline_handler", *args, **kwargs)

def watcher(*args, **kwargs):
    return _mark_method("is_watcher", *args, **kwargs)

def callback_handler(*args, **kwargs):
    return _mark_method("is_callback_handler", *args, **kwargs)

def raw_handler(*updates: TLObject):
    def inner(func: Command) -> Command:
        func.is_raw_handler = True
        func.updates = updates
        func.id = uuid4().hex
        return func

    return inner

def need_update(*update_types: BotUpdateType):
    def inner(func: Command) -> Command:
        func.is_bot_update_handler = True
        func.bot_update_types = list(update_types)
        func.id = uuid4().hex
        return func

    return inner

class Modules:
    def __init__(
        self,
        client: "CustomTelegramClient",
        db: Database,
    ):
        self._initial_registration = True
        self.commands = {}
        self.inline_handlers = {}
        self.callback_handlers = {}
        self.aliases = {}
        self.modules: list["Module" | None] = []                     
        self.libraries = []
        self.watchers = []
        self._log_handlers = []
        self._core_commands = []
        self.__approve = []
        self.client = client
        self._db = db
        self.db = db
        self.secure_boot = False
        asyncio.ensure_future(self._junk_collector())
        self.inline = InlineManager(self.client, self._db, self)
        self.client.heroku_inline = self.inline

    async def _junk_collector(self):
        while True:
            await asyncio.sleep(30)
            commands = {}
            inline_handlers = {}
            callback_handlers = {}
            watchers = []
            for module in self.modules:
                commands.update(module.heroku_commands)
                inline_handlers.update(module.heroku_inline_handlers)
                callback_handlers.update(module.heroku_callback_handlers)
                watchers.extend(module.heroku_watchers.values())

            self.commands = commands
            self.inline_handlers = inline_handlers
            self.callback_handlers = callback_handlers
            self.watchers = watchers

            logger.debug(
                (
                    "Reloaded %s commands,"
                    " %s inline handlers,"
                    " %s callback handlers and"
                    " %s watchers"
                ),
                len(self.commands),
                len(self.inline_handlers),
                len(self.callback_handlers),
                len(self.watchers),
            )

    async def register_all(
        self,
        mods: list[str] | None = None,
        no_external: bool = False,
    ) -> list[Module]:
        external_mods = []

        if not mods:
            mods = _iter_module_files(os.path.join(utils.get_base_dir(), MODULES_NAME))

            self.secure_boot = self._db.get(__name__, "secure_boot", False)

            external_mods = (
                []
                if self.secure_boot
                else [
                    Path(mod).resolve()
                    for mod in _iter_module_files(LOADED_MODULES_DIR)
                ]
            )

        loaded = []
        loaded += await self._register_modules(mods)

        if not no_external:
            loaded += await self._register_modules(external_mods, "<file>")

        return loaded

    @tag_client_id("client.tg_id")
    async def _register_modules(
        self,
        modules: list,
        origin: str = "<core>",
    ) -> list[Module]:
        loaded = []

        for mod in modules:
            try:
                mod_shortname = os.path.basename(mod).rsplit(".py", maxsplit=1)[0]
                module_name = f"{__package__}.{MODULES_NAME}.{mod_shortname}"
                user_friendly_origin = (
                    "<core {}>" if origin == "<core>" else "<file {}>"
                ).format(module_name)

                logger.debug("Loading %s from filesystem", module_name)

                spec = importlib.machinery.ModuleSpec(
                    module_name,
                    StringLoader(
                        Path(mod).read_text(encoding="utf-8"), user_friendly_origin
                    ),
                    origin=user_friendly_origin,
                )

                loaded += [await self.register_module(spec, module_name, origin)]

                logger.debug("Successfully loaded %s from filesystem", module_name)
            except Exception as e:
                logger.exception("Failed to load module %s due to %s:", mod, e)

        return loaded

    @tag_client_id("client.tg_id")
    async def register_module(
        self,
        spec: importlib.machinery.ModuleSpec,
        module_name: str,
        origin: str = "<core>",
        save_fs: bool = False,
    ) -> Module:
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module

        source_data = (
            spec.loader.data.decode()
            if hasattr(spec.loader, "data") and spec.loader.data
            else None
        )

        spec.loader.exec_module(module)

        ret = None

        ret = next(
            (
                value()
                for value in vars(module).values()
                if inspect.isclass(value) and issubclass(value, Module)
            ),
            None,
        )

        if hasattr(module, "__version__"):
            ret.__version__ = module.__version__

        if ret is None:
            ret = module.register(module_name)
            if not isinstance(ret, Module):
                raise TypeError(f"Instance is not a Module, it is {type(ret)}")

        ret.__origin__ = origin

        ret.__source__ = (
            source_data if source_data else inspect.getsource(ret.__class__)
        )

        if not hasattr(ret, "name"):
            ret.name = ret.strings["name"]

        await self.complete_registration(ret)

        cls_name = ret.__class__.__name__

        if save_fs and origin == "<string>":
            path = os.path.join(LOADED_MODULES_DIR, f"{cls_name}.py")
            Path(path).write_text(spec.loader.data.decode(), encoding="utf-8")
            logger.debug("Saved class %s to path %s", cls_name, path)

        return ret

    def add_aliases(self, aliases: dict):
        self.aliases.update(aliases)
        for alias, cmd in aliases.items():
            self.add_alias(alias, *cmd.split(maxsplit=1))

    def register_raw_handlers(self, instance: Module):
        for name, handler in utils.iter_attrs(instance):
            if getattr(handler, "is_raw_handler", False):
                self.client.dispatcher.raw_handlers.append(handler)
                logger.debug(
                    "Registered raw handler %s for %s. ID: %s",
                    name,
                    instance.__class__.__name__,
                    handler.id,
                )

    def register_bot_update_handlers(self, instance: Module):
        for name, handler in utils.iter_attrs(instance):
            if not getattr(handler, "is_bot_update_handler", False):
                continue

            for update_type in getattr(handler, "bot_update_types", []):
                self.inline.register_bot_update_handler(
                    f"{handler.id}_{update_type}",
                    update_type,
                    handler,
                )
                logger.debug(
                    "Registered bot update handler %s (%s) for module %s, update type %s",
                    name,
                    handler.id,
                    instance.__class__.__name__,
                    update_type,
                )

    def unregister_bot_update_handlers(self, instance: Module, purpose: str):
        for name, handler in utils.iter_attrs(instance):
            if not getattr(handler, "is_bot_update_handler", False):
                continue

            for update_type in getattr(handler, "bot_update_types", []):
                self.inline.unregister_bot_update_handler(f"{handler.id}_{update_type}")
                logger.debug(
                    "Unregistered bot update handler %s of module %s for %s",
                    name,
                    instance.__class__.__name__,
                    purpose,
                )

    @property
    def _remove_core_protection(self) -> bool:
        from . import main

        return self._db.get(main.__name__, "remove_core_protection", False)

    @tag_client_id("client.tg_id")
    def register_commands(self, instance: Module):
        if instance.__origin__.startswith("<core"):
            self._core_commands += list(
                map(lambda x: x.lower(), list(instance.heroku_commands))
            )

        for _command, cmd in instance.heroku_commands.items():

            if (
                not self._remove_core_protection
                and _command.lower() in self._core_commands
                and not instance.__origin__.startswith("<core")
            ):
                with contextlib.suppress(Exception):
                    self.modules.remove(instance)

                raise CoreOverwriteError(command=_command)

            self.commands.update({_command.lower(): cmd})

        for alias, cmd in self.aliases.copy().items():
            _cmd = cmd.split(maxsplit=1)
            if _cmd[0] in instance.heroku_commands:
                self.add_alias(alias, *_cmd)

        self.register_inline_stuff(instance)

    def register_inline_stuff(self, instance: Module):
        for name, func in instance.heroku_inline_handlers.copy().items():
            if name.lower() in self.inline_handlers:
                if (
                    hasattr(func, "__self__")
                    and hasattr(self.inline_handlers[name], "__self__")
                    and (
                        func.__self__.__class__.__name__
                        != self.inline_handlers[name].__self__.__class__.__name__
                    )
                ):
                    logger.debug(
                        "Duplicate inline_handler %s of %s",
                        name,
                        instance.__class__.__name__,
                    )

                logger.debug(
                    "Replacing inline_handler %s for %s",
                    self.inline_handlers[name],
                    instance.__class__.__name__,
                )

            self.inline_handlers.update({name.lower(): func})

        for name, func in instance.heroku_callback_handlers.copy().items():
            if name.lower() in self.callback_handlers and (
                hasattr(func, "__self__")
                and hasattr(self.callback_handlers[name], "__self__")
                and func.__self__.__class__.__name__
                != self.callback_handlers[name].__self__.__class__.__name__
            ):
                logger.debug(
                    "Duplicate callback_handler %s of %s",
                    name,
                    instance.__class__.__name__,
                )

            self.callback_handlers.update({name.lower(): func})

    def unregister_inline_stuff(self, instance: Module, purpose: str):
        for name, func in instance.heroku_inline_handlers.copy().items():
            if name.lower() in self.inline_handlers and (
                hasattr(func, "__self__")
                and hasattr(self.inline_handlers[name], "__self__")
                and func.__self__.__class__.__name__
                == self.inline_handlers[name].__self__.__class__.__name__
            ):
                del self.inline_handlers[name.lower()]
                logger.debug(
                    "Unregistered inline_handler %s of %s for %s",
                    name,
                    instance.__class__.__name__,
                    purpose,
                )

        for name, func in instance.heroku_callback_handlers.copy().items():
            if name.lower() in self.callback_handlers and (
                hasattr(func, "__self__")
                and hasattr(self.callback_handlers[name], "__self__")
                and func.__self__.__class__.__name__
                == self.callback_handlers[name].__self__.__class__.__name__
            ):
                del self.callback_handlers[name.lower()]
                logger.debug(
                    "Unregistered callback_handler %s of %s for %s",
                    name,
                    instance.__class__.__name__,
                    purpose,
                )

    @tag_client_id("client.tg_id")
    def register_watchers(self, instance: Module):
        for _watcher in self.watchers:
            if _watcher.__self__.__class__.__name__ == instance.__class__.__name__:
                logger.debug("Removing watcher %s for update", _watcher)
                self.watchers.remove(_watcher)

        for _watcher in instance.heroku_watchers.values():
            self.watchers += [_watcher]

    def lookup(
        self,
        modname: str,
    ) -> bool | Module | Library:
        return next(
            (lib for lib in self.libraries if lib.name.lower() == modname.lower()),
            False,
        ) or next(
            (
                mod
                for mod in self.modules
                if mod.__class__.__name__.lower() == modname.lower()
                or getattr(mod, "name", "").lower() == modname.lower()
            ),
            False,
        )

    @property
    def get_approved_channel(self):
        return self.__approve.pop(0) if self.__approve else None

    def get_prefix(self, ent_id: int = None) -> str:
        from . import main

        key = main.__name__
        default = "."

        if ent_id:
            prefixes = self._db.get(key, "command_prefixes", {})
            result = prefixes.get(str(ent_id), default)
        else:
            result = self._db.get(key, "command_prefix", default)
        return result

    def get_prefixes(self) -> set[str]:
        from . import main

        key = main.__name__
        default = "."

        prefixes = ()
        prefixes += tuple(self._db.get(key, "command_prefixes", {}).values())
        prefixes += tuple(self._db.get(key, "command_prefix", default))

        return set(prefixes)

    @tag_client_id("client.tg_id")
    async def complete_registration(self, instance: Module):
        instance.allmodules = self
        instance.internal_init()

        for module in self.modules:
            if module.__class__.__name__ == instance.__class__.__name__:
                if not self._remove_core_protection and module.__origin__.startswith(
                    "<core"
                ):
                    raise CoreOverwriteError(
                        module=(
                            module.__class__.__name__[:-3]
                            if module.__class__.__name__.endswith("Mod")
                            else module.__class__.__name__
                        )
                    )

                logger.debug("Removing module %s for update", module)
                await module.on_unload()

                self.unregister_raw_handlers(module, "update")
                self.unregister_bot_update_handlers(module, "update")
                self.unregister_loops(module, "update")

                self.modules.remove(module)

        self.modules += [instance]

    def find_alias(
        self,
        alias: str,
        include_legacy: bool = False,
    ) -> str | None:
        if not alias:
            return None

        for command_name, _command in self.commands.items():
            aliases = []
            if getattr(_command, "alias", None) and not (
                aliases := getattr(_command, "aliases", None)
            ):
                aliases = [_command.alias]

            if not aliases:
                continue

            if any(
                alias.lower() == _alias.lower()
                and alias.lower() not in self._core_commands
                for _alias in aliases
            ):
                return command_name

        if alias in self.aliases and include_legacy:
            return self.aliases[alias]

        return None

    def dispatch(self, _command: str) -> tuple[str, str | None]:
        resolved = next(
            (
                (cmd, self.commands[cmd.split()[0].lower()])
                for cmd in [
                    _command,
                    self.aliases.get(_command.lower()),
                    self.find_alias(_command),
                ]
                if cmd and cmd.split()[0].lower() in self.commands
            ),
            (_command, None),
        )

        cmd, func = resolved
        if not func:
            return resolved

        try:
            disabled_modules = self._db.get(main.__name__, "disabled_modules", [])
            disabled_commands = self._db.get(main.__name__, "disabled_commands", {})
        except Exception:
            disabled_modules = []
            disabled_commands = {}

        module_name = None
        try:
            module_name = func.__self__.__class__.__name__
        except Exception:
            module_name = None

        if module_name and module_name in disabled_modules:
            return (_command, None)

        if module_name and module_name in disabled_commands:
            disabled_for_mod = [
                x.lower() for x in disabled_commands.get(module_name, [])
            ]
            if cmd.split()[0].lower() in disabled_for_mod:
                return (_command, None)

        return (cmd, func)

    def send_config(self, skip_hook: bool = False):
        for mod in self.modules:
            self.send_config_one(mod, skip_hook)

    @tag_client_id("client.tg_id")
    def send_config_one(self, mod: Module, skip_hook: bool = False):
        if hasattr(mod, "config"):
            modcfg = self._db.get(
                mod.__class__.__name__,
                "__config__",
                {},
            )
            try:
                for conf in mod.config:
                    with contextlib.suppress(validators.ValidationError):
                        mod.config.set_no_raise(
                            conf,
                            (
                                modcfg[conf]
                                if conf in modcfg
                                else os.environ.get(f"{mod.__class__.__name__}.{conf}")
                                or mod.config.getdef(conf)
                            ),
                        )
            except AttributeError:
                logger.warning(
                    "Got invalid config instance. Expected `ModuleConfig`, got %s, %s",
                    type(mod.config),
                    mod.config,
                )

        if not hasattr(mod, "name"):
            mod.name = mod.strings["name"]

        if skip_hook:
            return

        if not hasattr(mod, "strings"):
            mod.strings = {}

        mod.strings = Strings(mod)

        try:
            mod.config_complete()
        except Exception as e:
            logger.exception("Failed to send mod config complete signal due to %s", e)
            raise

    async def send_ready_one_wrapper(self, *args, **kwargs):
        try:
            await self.send_ready_one(*args, **kwargs)
        except Exception as e:
            logger.exception("Failed to send mod init complete signal due to %s", e)

    async def send_ready(self):
        await asyncio.gather(
            *[self.send_ready_one_wrapper(mod) for mod in self.modules]
        )

    @tag_client_id("client.tg_id")
    async def send_ready_one(
        self,
        mod: Module,
        no_self_unload: bool = False,
        from_dlmod: bool = False,
    ):
        if from_dlmod:
            try:
                if len(inspect.signature(mod.on_dlmod).parameters) == 2:
                    await mod.on_dlmod(self.client, self._db)
                else:
                    await mod.on_dlmod()
            except Exception:
                logger.info("Can't process `on_dlmod` hook", exc_info=True)

        try:
            if len(inspect.signature(mod.client_ready).parameters) == 2:
                await mod.client_ready(self.client, self._db)
            else:
                await mod.client_ready()
        except SelfUnload as e:
            if no_self_unload:
                raise e

            logger.debug("Unloading %s, because it raised SelfUnload", mod)
            self.modules.remove(mod)
            return
        except SelfSuspend as e:
            if no_self_unload:
                raise e

            logger.debug("Suspending %s, because it raised SelfSuspend", mod)
            return
        except Exception as e:
            logger.exception(
                (
                    "Failed to send mod init complete signal for %s due to %s,"
                    " attempting unload"
                ),
                mod,
                e,
            )
            self.modules.remove(mod)
            raise

        for _, method in utils.iter_attrs(mod):
            if isinstance(method, InfiniteLoop):
                setattr(method, "module_instance", mod)

                if method.autostart and not self._db.get(
                    main.__name__, "heroku_disabled", False
                ):
                    method.start()

                logger.debug("Added module %s to method %s", mod, method)

        self.unregister_commands(mod, "update")
        self.unregister_raw_handlers(mod, "update")
        self.unregister_bot_update_handlers(mod, "update")

        self.register_commands(mod)
        self.register_watchers(mod)
        self.register_raw_handlers(mod)
        self.register_bot_update_handlers(mod)

    def get_classname(self, name: str) -> str:
        return next(
            (
                module.__class__.__module__
                for module in reversed(self.modules)
                if name in (module.name, module.__class__.__module__)
            ),
            name,
        )

    @tag_client_id("client.tg_id")
    async def unload_module(self, classname: str) -> list[str]:
        worked = []

        for module in self.modules:
            if classname.lower() in (
                module.name.lower(),
                module.__class__.__name__.lower(),
            ):
                if not self._remove_core_protection and module.__origin__.startswith(
                    "<core"
                ):
                    raise CoreUnloadError(module.__class__.__name__)

                worked += [module.__class__.__name__]

                name = module.__class__.__name__
                path = os.path.join(LOADED_MODULES_DIR, f"{name}.py")

                if os.path.isfile(path):
                    os.remove(path)
                    logger.debug("Removed %s file at path %s", name, path)

                logger.debug("Removing module %s for unload", module)
                self.modules.remove(module)

                await module.on_unload()

                self.unregister_raw_handlers(module, "unload")
                self.unregister_bot_update_handlers(module, "unload")
                self.unregister_loops(module, "unload")
                self.unregister_commands(module, "unload")
                self.unregister_watchers(module, "unload")
                self.unregister_inline_stuff(module, "unload")

        logger.debug("Worked: %s", worked)
        return worked

    def unregister_loops(self, instance: Module, purpose: str):
        for name, method in utils.iter_attrs(instance):
            if isinstance(method, InfiniteLoop):
                logger.debug(
                    "Stopping loop for %s in module %s, method %s",
                    purpose,
                    instance.__class__.__name__,
                    name,
                )
                method.stop()

    def unregister_commands(self, instance: Module, purpose: str):
        for name, cmd in self.commands.copy().items():
            if cmd.__self__.__class__.__name__ == instance.__class__.__name__:
                logger.debug(
                    "Removing command %s of module %s for %s",
                    name,
                    instance.__class__.__name__,
                    purpose,
                )
                del self.commands[name]
                for alias, _command in self.aliases.copy().items():
                    if _command == name:
                        del self.aliases[alias]

    def unregister_watchers(self, instance: Module, purpose: str):
        for _watcher in self.watchers.copy():
            if _watcher.__self__.__class__.__name__ == instance.__class__.__name__:
                logger.debug(
                    "Removing watcher %s of module %s for %s",
                    _watcher,
                    instance.__class__.__name__,
                    purpose,
                )
                self.watchers.remove(_watcher)

    def unregister_raw_handlers(self, instance: Module, purpose: str):
        for handler in self.client.dispatcher.raw_handlers:
            if handler.__self__.__class__.__name__ == instance.__class__.__name__:
                self.client.dispatcher.raw_handlers.remove(handler)
                logger.debug(
                    "Unregistered raw handler of module %s for %s. ID: %s",
                    instance.__class__.__name__,
                    purpose,
                    handler.id,
                )

    def add_alias(self, alias: str, cmd: str, args: str = None) -> bool:
        if cmd not in self.commands:
            return False

        self.aliases[alias.lower().strip()] = f"{cmd} {args}" if args else cmd
        return True

    def remove_alias(self, alias: str) -> bool:
        return bool(self.aliases.pop(alias.lower().strip(), None))

    async def log(self, *args, **kwargs):
        pass
    async def reload_translations(self) -> bool:
        return True
