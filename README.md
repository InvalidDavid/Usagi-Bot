# Y-K-Bot

A Py-cord bot for the Yuki / Yumemi / Kotatsu Discord server.

## Local Setup

Use Python 3.13 for this project. Python 3.14 is currently too new for the Bot's Py-cord stack and can break local startup.

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

If you already created `.venv` with another Python version, remove it and recreate it with Python 3.13 before installing dependencies again.

## Architecture

The runtime entrypoint stays in `main.py`, while the implementation now lives in a modular internal package:

```text
.
├── cog/                     # Thin extension wrappers for Discord cog loading
├── internal/
│   ├── cogs/                # Actual cog implementations
│   │   └── moderation/      # Split moderation command domains
│   ├── services/            # External API and persistence logic
│   ├── utils/               # Shared helpers
│   └── views/               # Discord UI views and modals
├── main.py                  # Entry point
└── requirements.txt
```

> [!NOTE]
> - The moderation database now creates the `Data/` directory automatically.
> - Forum and role settings are read safely from `.env` through the shared config loader.
> - The `cog/` files are intentionally small so owner reload commands still work against the modular internal package.
