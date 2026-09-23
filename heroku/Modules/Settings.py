# CopyLeft 2026 github.com/i-execute // i_execute.t.me
# Licensed under AGPLv3.

__version__ = (2, 1, 3)
# meta developer: Execute_forge.t.me
# meta banner: https://raw.githubusercontent.com/i-execute/Modules/main/Storage/Info/MetaBanner.jpeg

# (c) Dan Gazizullin, 2021-2023. This file is part of the Hikka Userbot: github.com/hikariatama/Hikka

from telethon.tl.types import Message, User

from .. import loader, main, utils

@loader.tds
class Settings(loader.Module):
    """Control core userbot settings"""

    strings = {
        "name": "Settings",
        "what_prefix": "<b>What should the prefix be set to?</b>",
        "prefix_incorrect": "<b>Prefix must be one symbol in length</b>",
        "prefix_set": "{} <b>Command prefix updated. Use the following command to change it back:</b>\n<pre><code class=\"language-heroku\">{newprefix}setprefix {oldprefix}</code></pre>",
        "entity_prefix_set": "{} <b>Command prefix updated for {entity_name}. Use the following command to change it back:</b>\n<pre><code class=\"language-heroku\">{newprefix}setprefix {oldprefix} {entity_id}</code></pre>",
        "id_not_found_scgroup": "This entity does not exist in any security group. Therefore, adding a prefix for it is pointless",
        "invalid_id_or_username": "Invalid id/username was given",
        "alias_created": "<b>Alias created. Access it with</b> <code>{}</code>",
        "aliases_created": "<b>Added {count} aliases:</b>\n<blockquote expandable>{aliases}</blockquote>",
        "aliases_created_line": "{aliases} for {command}",
        "aliases": "<b> Aliases:</b>",
        "no_command": "<b>Command</b> <code>{}</code> <b>does not exist</b>",
        "alias_exists": "<b>Alias</b> <code>{alias}</code> <b>already exists for command</b> <code>{command}</code>",
        "alias_args": "<b>You must provide a command and the alias for it</b>",
        "delalias_args": "<b>You must provide the alias name</b>",
        "alias_removed": "<b>Alias</b> <code>{}</code> <b>removed</b>.",
        "aliases_removed": "<b>Removed {count} aliases:</b>\n<blockquote expandable>{aliases}</blockquote>",
        "aliases_cleared": "<b>All aliases removed</b>.",
        "no_alias": "<b>Alias</b> <code>{}</code> <b>does not exist</b>",
        "not_a_user": "<b>The entity {} is not a user</b>",
        "_cmd_doc_addalias": "Set an alias for a command",
        "_cmd_doc_delalias": "<alias|-c|--clear> - Remove an alias or clear all aliases",
        "_cmd_doc_setprefix": "<prefix> [owner] - Sets command prefix",
        "_cfg_rich_mode": "Show Heroku as a Rich message.",
        "_cls_doc": "Control core userbot settings",
        "_cfg_backup_period": "Automatic backup period in hours (1 3 6 9 12 24 48 168). 0 disables backups",
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "backup_period",
                0,
                lambda: self.strings["_cfg_backup_period"],
                validator=loader.validators.Integer(minimum=0),
            ),
            loader.ConfigValue(
                "allow_nonstandart_prefixes",
                False,
                "Allow non-standard prefixes like premium emojis or multi-symbol prefixes",
                validator=loader.validators.Boolean(),
            ),
            loader.ConfigValue(
                "alias_emoji",
                "",
                "just emoji in .aliases",
            ),
            loader.ConfigValue(
                "rich_mode",
                False,
                lambda: self.strings["_cfg_rich_mode"],
                validator=loader.validators.Boolean(),
            ),
        )

    @loader.command()
    async def setprefix(self, message: Message):
        if not (args := utils.get_args(message)):
            await utils.answer(message, self.strings["what_prefix"])
            return

        if len(args[0]) != 1 and self.config.get("allow_nonstandart_prefixes") is False:
            await utils.answer(message, self.strings["prefix_incorrect"])
            return

        if args[0] == "s":
            await utils.answer(message, self.strings["prefix_incorrect"])
            return

        if len(args) == 2:
            if args[1].isdigit():
                args[1] = int(args[1])
            try:
                entity = await self.client.get_entity(args[1])
            except Exception:
                return await utils.answer(
                    message, self.strings["invalid_id_or_username"]
                )

            if not isinstance(entity, User):
                return await utils.answer(
                    message, self.strings["not_a_user"].format(args[1])
                )

            if entity.id != self.tg_id:
                sgroup_users = []
                for g in self._client.dispatcher.security._sgroups.values():
                    for u in g.users:
                        sgroup_users.append(u)

                tsec_users = [
                    rule["target"]
                    for rule in self._client.dispatcher.security._tsec_user
                ]
                ub_owners = self._client.dispatcher.security.owner.copy()

                all_users = sgroup_users + tsec_users + ub_owners

                if entity.id not in all_users:
                    return await utils.answer(
                        message, self.strings["id_not_found_scgroup"]
                    )

                oldprefix = utils.escape_html(self.get_prefix(entity.id))
                all_prefixes = self._db.get(
                    main.__name__,
                    "command_prefixes",
                    {},
                )

                all_prefixes[str(entity.id)] = args[0]

                self._db.set(
                    main.__name__,
                    "command_prefixes",
                    all_prefixes,
                )
                return await utils.answer(
                    message,
                    self.strings["entity_prefix_set"].format(
                        "",
                        entity_name=utils.escape_html(entity.first_name),
                        newprefix=utils.escape_html(args[0]),
                        oldprefix=utils.escape_html(oldprefix),
                        entity_id=args[1],
                    ),
                )

        oldprefix = utils.escape_html(self.get_prefix())

        self._db.set(
            main.__name__,
            "command_prefix",
            args[0],
        )
        await utils.answer(
            message,
            self.strings["prefix_set"].format(
                "",
                newprefix=utils.escape_html(args[0]),
                oldprefix=utils.escape_html(oldprefix),
            ),
        )

    @loader.command()
    async def addalias(self, message: Message):

        args_raw = utils.get_args_raw(message)
        if not args_raw:
            await utils.answer(message, self.strings["alias_args"])
            return

        import keyword

        def parse_alias_line(line: str) -> tuple[list[str], str] | None:
            line = line.strip()
            if not line:
                return None

            if "&&" in line:
                parts = line.split("&&", 1)
                alias_part, command_part = parts[0].strip(), parts[1].strip()
                aliases = [a.strip().lower() for a in alias_part.split(",") if a.strip()]
                return aliases, command_part
            elif "," in line:
                parts = [part.strip() for part in line.split(",")]
                if parts:
                    last = parts[-1].split(maxsplit=1)
                    if len(last) >= 2:
                        aliases = [part.lower() for part in parts[:-1] if part]
                        aliases.append(last[0].lower())
                        return aliases, last[1]
            else:
                args = line.split(maxsplit=1)
                if len(args) >= 2:
                    return [args[0].lower()], args[1]
            return None

        alias_lines = []
        lines = args_raw.splitlines()

        for line_idx, line in enumerate(lines):
            is_new_alias = False
            parsed_aliases = None
            parsed_cmd = None
            parsed_rest = None

            stripped_line = line.strip()
            if stripped_line:
                parsed = parse_alias_line(line)
                if parsed:
                    aliases, command = parsed
                    command_parts = command.split(maxsplit=1)
                    cmd = command_parts[0]
                    rest = command_parts[1] if len(command_parts) > 1 else None

                    first_word = stripped_line.split()[0] if stripped_line else ""
                    is_valid_candidate = (
                        not line.startswith(" ")
                        and not line.startswith("\t")
                        and not keyword.iskeyword(first_word)
                        and all(c.isalnum() or c in "_-" for c in first_word)
                    )

                    if is_valid_candidate and cmd in self.allmodules.commands:
                        is_new_alias = True
                        parsed_aliases = aliases
                        parsed_cmd = cmd
                        parsed_rest = rest

            if line_idx == 0:
                parsed = parse_alias_line(line)
                if not parsed:
                    await utils.answer(message, self.strings["alias_args"])
                    return
                aliases, command = parsed
                command_parts = command.split(maxsplit=1)
                cmd = command_parts[0]
                rest = command_parts[1] if len(command_parts) > 1 else None

                if cmd not in self.allmodules.commands:
                    await utils.answer(
                        message,
                        self.strings["no_command"].format(utils.escape_html(cmd)),
                    )
                    return

                alias_lines.append((aliases, cmd, rest))
            else:
                if is_new_alias:
                    alias_lines.append((parsed_aliases, parsed_cmd, parsed_rest))
                else:
                    if alias_lines:
                        aliases, cmd, rest = alias_lines[-1]
                        if rest is None:
                            new_rest = line
                        else:
                            new_rest = rest + "\n" + line
                        alias_lines[-1] = (aliases, cmd, new_rest)

        if not alias_lines:
            await utils.answer(message, self.strings["alias_args"])
            return

        added_lines = []
        skipped_lines = []
        planned_aliases = {}
        stored_aliases = {**self.get("aliases", {})}

        for aliases, cmd, rest in alias_lines:
            target = f"{cmd} {rest}" if rest else cmd
            added_aliases = []

            for alias in aliases:
                if alias in self.allmodules.aliases:
                    skipped_lines.append(
                        self.strings["alias_exists"].format(
                            alias=utils.escape_html(alias),
                            command=utils.escape_html(self.allmodules.aliases[alias]),
                        )
                    )
                    continue

                if alias in planned_aliases:
                    skipped_lines.append(
                        self.strings["alias_exists"].format(
                            alias=utils.escape_html(alias),
                            command=utils.escape_html(planned_aliases[alias]),
                        )
                    )
                    continue

                if not self.allmodules.add_alias(alias, cmd, rest):
                    await utils.answer(
                        message,
                        self.strings["no_command"].format(utils.escape_html(cmd)),
                    )
                    return

                stored_aliases[alias] = target
                planned_aliases[alias] = target
                added_aliases.append(alias)

            if added_aliases:
                added_lines.append((added_aliases, target))

        if added_lines:
            self.set("aliases", stored_aliases)

        if len(added_lines) == 1 and len(added_lines[0][0]) == 1 and not skipped_lines:
            await utils.answer(
                message,
                self.strings["alias_created"].format(
                    utils.escape_html(added_lines[0][0][0])
                ),
            )
            return

        added_count = sum(len(aliases) for aliases, _ in added_lines)
        response = []

        if added_lines:
            response.append(
                self.strings["aliases_created"].format(
                    count=added_count,
                    aliases="\n".join(
                        self.strings["aliases_created_line"].format(
                            aliases=utils.escape_html(", ".join(aliases)),
                            command=utils.escape_html(target),
                        )
                        for aliases, target in added_lines
                    ),
                )
            )

        response.extend(skipped_lines)

        await utils.answer(message, "\n\n".join(response))

    @loader.command()
    async def delalias(self, message: Message):
        args_raw = utils.get_args_raw(message)

        if not args_raw:
            await utils.answer(message, self.strings["delalias_args"])
            return

        if args_raw.strip() in {"-c", "--clear"}:
            self.allmodules.aliases.clear()
            self.set("aliases", {})
            await utils.answer(message, self.strings["aliases_cleared"])
            return

        aliases = []
        seen_aliases = set()
        for line in args_raw.splitlines():
            for alias in line.split(","):
                alias = alias.lower().strip()
                if alias and alias not in seen_aliases:
                    aliases.append(alias)
                    seen_aliases.add(alias)

        if not aliases:
            await utils.answer(message, self.strings["delalias_args"])
            return

        current = self.get("aliases", {})
        removed_aliases = []
        missed_aliases = []

        for alias in aliases:
            if not self.allmodules.remove_alias(alias):
                missed_aliases.append(alias)
                continue

            current.pop(alias, None)
            removed_aliases.append(alias)

        if removed_aliases:
            self.set("aliases", current)

        if len(removed_aliases) == 1 and not missed_aliases:
            await utils.answer(
                message,
                self.strings["alias_removed"].format(
                    utils.escape_html(removed_aliases[0])
                ),
            )
            return

        response = []
        if removed_aliases:
            response.append(
                self.strings["aliases_removed"].format(
                    count=len(removed_aliases),
                    aliases=utils.escape_html(", ".join(removed_aliases)),
                )
            )

        response.extend(
            self.strings["no_alias"].format(utils.escape_html(alias))
            for alias in missed_aliases
        )

        await utils.answer(
            message,
            "\n\n".join(response),
        )

