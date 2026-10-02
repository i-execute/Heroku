# Heroku Userbot

Heroku is a modular Telegram userbot based on Telethon.

## Requirements

- Python 3.11 or newer
- A Telegram API ID and API hash from `my.telegram.org`
- A Telegram bot created by the user
- Inline mode enabled for that bot
- Git and a supported Linux environment

The project does not create bots, search BotFather chats, revoke tokens, configure avatars, or enable inline mode automatically.

## Installation

```bash
git clone https://github.com/i-execute/Heroku.git
cd Heroku
python3 -m venv venv
. venv/bin/activate
python3 -m pip install -r Storage/requirements.txt
python3 -m heroku
```

On startup, enter the API credentials and bot token in the terminal. The token is checked by Telegram before it is saved. Startup also verifies that inline mode is enabled.

Open the supplied bot and follow the setup prompts. Authorization can be completed with either a QR code or a phone number, login code, and 2FA password. Inline input marker messages are deleted through the authorized user account.

## Running as a service

Create a user service and adjust the paths if the repository is installed elsewhere:

```bash
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/heroku.service <<'EOF'
[Unit]
Description=Heroku Userbot
After=network-online.target

[Service]
WorkingDirectory=%h/Heroku
ExecStart=%h/Heroku/venv/bin/python3 -m heroku
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
EOF
systemctl --user daemon-reload
systemctl --user enable --now heroku.service
```

## Updating

There is no automatic updater. Update the repository and restart the process or service manually:

```bash
git pull --ff-only
sudo systemctl restart heroku.service
```

## Removal

Run the removal script from the repository:

```bash
bash Storage/Nuke.sh
```

The script validates its installation path, removes the matching systemd unit, removes the repository, and stops the running userbot process when applicable.

## Backups

A full database and module backup is sent immediately after startup and then every hour. Backups exclude only `heroku.inline.bot_token`. Keys named `bot_token` that belong to other modules remain unchanged. The terminal token is never restored or migrated from a backup.

## Tests

```bash
python3 tests/test_botpm_ask.py
python3 tests/test_botpm_article_shape.py
python3 tests/test_bot_token_backup.py
python3 tests/test_inline_marker_cleanup.py
python3 tests/test_module_persistence.py
python3 tests/test_dlmall_repo.py
python3 tests/test_restore_backup.py
python3 tests/test_telethon_preview.py
python3 tests/test_refactor_contract.py
```

## License

This project is distributed under the GNU Affero General Public License v3.0. See `LICENSE` for details.
