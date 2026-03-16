from __future__ import annotations

import importlib
import sys
from collections.abc import Callable


def _import_fresh(module_name: str):
    module_names = [
        name
        for name in sys.modules
        if name == module_name or name.startswith(f"{module_name}.")
    ]
    for name in sorted(module_names, reverse=True):
        sys.modules.pop(name, None)
    return importlib.import_module(module_name)


def setup_proxy(module_name: str) -> Callable:
    def setup(bot):
        module = _import_fresh(module_name)
        module.setup(bot)

    return setup
