from __future__ import annotations

from pathlib import Path


def extension_names(folder: str = "cog") -> list[str]:
    base_path = Path(folder)
    if not base_path.is_dir():
        return []
    return sorted(
        path.stem
        for path in base_path.glob("*.py")
        if not path.name.startswith("_")
    )


def extension_module(name: str, folder: str = "cog") -> str:
    return f"{folder}.{name}"


def is_extension_loaded(bot, name: str, folder: str = "cog") -> bool:
    return extension_module(name, folder) in bot.extensions


def load_all_extensions(bot, folder: str = "cog") -> dict[str, Exception | None]:
    results: dict[str, Exception | None] = {}
    for name in extension_names(folder):
        try:
            bot.load_extension(extension_module(name, folder))
            results[name] = None
        except Exception as exc:  # pragma: no cover - startup logging path
            results[name] = exc
    return results
