# Y-K-Bot

A Py-cord bot for the Yuki / Kotatsu Discord server.

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
