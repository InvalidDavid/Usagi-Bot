from __future__ import annotations

from datetime import datetime

import discord

from .ansi import BLUE, block


def make_embed(
    title: str,
    color: discord.Color,
    description: str | None = None,
    *,
    timestamp: datetime | None = None,
) -> discord.Embed:
    return discord.Embed(
        title=title,
        color=color,
        description=description,
        timestamp=timestamp,
    )


def add_ansi_field(
    embed: discord.Embed,
    name: str,
    value: str,
    *,
    color: str = BLUE,
    inline: bool = False,
) -> None:
    embed.add_field(name=name, value=block(str(value), color), inline=inline)
