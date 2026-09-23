# CopyLeft 2026 github.com/i-execute // i_execute.t.me
# Licensed under AGPLv3.

# Inline-unit service strings (formerly langpacks/en.json inline.* keys).

from __future__ import annotations


class _ServiceStrings:
    """Mirrors the Strings call surface: getkey/getdict/gettext."""

    _S = {
        "opening_form": "<b>Opening form...</b>",
        "opening_gallery": "<b>Opening gallery...</b>",
        "opening_list": "<b>Opening list...</b>",
        "inline403": "<b>You can't send inline units in this chat</b>",
        "invoke_failed": "<b>Unit invoke failed! More info in logs</b>",
        "invoke_failed_logs": "<b>Unit invoke failed!</b>\n\n<b>Logs:</b>\n\n<pre><code class=\"language-logs\">{}</code></pre>",
        "show_inline_cmds": "Show all available inline commands",
        "no_inline_cmds": "You have no available commands",
        "no_inline_cmds_msg": "<b> There are no available inline commands or you lack access to them</b>",
        "inline_cmds": "You have {} available command(-s)",
        "inline_cmds_msg": "<b>Available inline commands:</b>\n\n{}",
        "run_command": "Run command",
        "command_msg": "<b> Command «{}»</b>\n\n<i>{}</i>",
        "command": "Command «{}»",
        "button403": "You are not allowed to press this button!",
        "keep_id": "Do not remove ID! {}",
        "no_query_results": "<b>Failed to create form</b>\n\nPossible ways to fix the error:\n\n1. Restart Heroku: <code>{prefix}restart</code>\n\n2. Enable inline mode for the bot: go to @BotFather, send /mybots, click Bot Settings -> Inline Mode -> On\n\n3. Create a new bot: send the command <code>{prefix}ch_heroku_bot</code> <@botname>",
    }

    def getkey(self, key: str, **kwargs) -> str:
        return self._S.get(key[len("inline.") :] if key.startswith("inline.") else key, key).format(
            **kwargs
        ) if kwargs else self._S.get(key[len("inline.") :] if key.startswith("inline.") else key, key)

    def getdict(self, key: str, **kwargs) -> dict:
        return {"en": self.getkey(key, **kwargs)}

    def gettext(self, text: str) -> str:
        return self._S.get(text, text)
