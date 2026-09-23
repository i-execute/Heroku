# CopyLeft 2026 github.com/i-execute // i_execute.t.me
# Licensed under AGPLv3.

# (c) Dan Gazizullin, 2021-2023. This file is part of the Hikka Userbot: github.com/hikariatama/Hikka

# Compatibility alias: external modules import `herokutl`, the fork is vanilla
# telethon. Maps herokutl.<path> -> telethon.<path> lazily.

import sys
import types


class _HerokutlModule(types.ModuleType):
    def __getattr__(self, name: str):
        import telethon

        try:
            real = getattr(telethon, name)
        except AttributeError:
            raise AttributeError(f"module 'herokutl' has no attribute '{name}'") from None

        setattr(self, name, real)
        return real


def _install() -> None:
    if "herokutl" in sys.modules:
        return

    herokutl = _HerokutlModule("herokutl")
    herokutl.__path__ = []  # mark as package so submodule imports resolve
    sys.modules["herokutl"] = herokutl


def _install_submodule(name: str) -> types.ModuleType:
    import telethon

    real = telethon
    for part in name.split("."):
        real = getattr(real, part)

    mod = sys.modules.get(f"herokutl.{name}")
    if mod is not None and type(mod) is _HerokutlModule:
        return mod

    mod = _HerokutlModule(f"herokutl.{name}")
    mod.__dict__.update(
        {k: v for k, v in vars(real).items() if not k.startswith("__")}
    )
    sys.modules[f"herokutl.{name}"] = mod
    return mod


_install()

for _path in (
    "errors",
    "errors.common",
    "errors.rpcerrorlist",
    "network",
    "network.requeststate",
    "tl",
    "tl.tlobject",
    "tl.types",
    "types",
):
    _install_submodule(_path)
