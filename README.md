<p align="center">
  <a href="https://t.me/I_execute"><img src="https://img.shields.io/badge/Telegram-@I__execute-26A5E4?style=flat&logo=telegram&logoColor=white" alt="Telegram" /></a>
</p>

# Heroku

Telegram userbot on Telethon. Personal fork, cleaned up.

## Install

```bash
cd ~
git clone https://github.com/i-execute/Heroku
cd Heroku
python3 -m venv venv
source venv/bin/activate
pip install -r Storage/requirements.txt
python3 -m heroku
```

Requires Python 3.12+ and git. On first start: API ID/hash from https://my.telegram.org, then your phone.

### systemd (user)

```bash
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/heroku.service << EOF
[Unit]
Description=Heroku Userbot
After=network.target

[Service]
WorkingDirectory=$HOME/Heroku
ExecStart=$HOME/Heroku/venv/bin/python3 -m heroku
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now heroku
```

For root:

```bash
cat > /etc/systemd/system/heroku.service << EOF
[Unit]
Description=Heroku Userbot
After=network.target

[Service]
WorkingDirectory=/root/Heroku
ExecStart=/root/Heroku/venv/bin/python3 -m heroku
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now heroku
```

## Update

```bash
git pull
```

Or `.update` from Telegram (manual only, no auto-updater).

## Differences from upstream

- Telethon 1.45 instead of herokutl; no patchers, no unix-socket proxy layer
- Single client; no Docker, install scripts, QR login, banners
- JSON langpacks: English, Russian, Chinese
- `.dlm` loads files only, no URLs; Loader renamed to Installer
- Manual `.update` only; no comments in code

## Crypto

Upstream shipped `TgCrypto-pyrofork` in requirements — a package neither Telethon nor herokutl ever imports. Without `cryptg`, everything silently falls back to pure-Python pyaes: **3.1 s** for 16 MB of AES-IGE. Replaced with `cryptg` (written by Telethon's author).

| Stack | 4KB | 1MB | 16MB |
|---|---|---|---|
| GoyGram (Rust, AES-NI) | 0.004 ms | 3.0 ms | 62 ms |
| **cryptg (used here)** | 0.010 ms | 4.5 ms | 88 ms |
| TgCrypto-pyrofork (upstream) | 0.016 ms | 7.1 ms | 151 ms |
| pyaes (fallback) | 16.6 ms | 3497 ms | — |

Benchmark: `tests/bench_crypto.py`. All stacks produce byte-identical ciphertext.

## Tests

```bash
python3 tests/test_dlm_lifecycle.py
python3 tests/bench_crypto.py cryptg
```

## License

AGPLv3
