from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from plugins import JarvisTool


class PluginLoader:
    """Discover and import plugin files from the /plugins directory."""

    def __init__(self, plugins_dir: str = "plugins") -> None:
        self._dir = Path(plugins_dir).resolve()
        self._loaded: list[str] = []
        self._errors: list[str] = []

    def load_all(self) -> int:
        """Import every *.py file in the plugins dir (skips _private files)."""
        for path in sorted(self._dir.glob("*.py")):
            if path.name.startswith("_"):
                continue
            self._load(path)
        return len(self._loaded)

    def _load(self, path: Path) -> None:
        module_name = f"_jarvis_plugin_{path.stem}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, path)
            if spec is None or spec.loader is None:
                self._errors.append(f"{path.name}: no spec")
                return
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)  # type: ignore[union-attr]
            self._loaded.append(path.stem)
        except Exception as e:
            self._errors.append(f"{path.name}: {e}")

    def get_tools(self) -> dict:
        from plugins import all_tools
        return all_tools()

    def reload(self) -> int:
        """Clear and re-import all plugins (useful for hot-reload)."""
        from plugins import _REGISTRY
        _REGISTRY.clear()
        self._loaded.clear()
        self._errors.clear()
        # Remove cached plugin modules
        for key in [k for k in sys.modules if k.startswith("_jarvis_plugin_")]:
            del sys.modules[key]
        return self.load_all()

    @property
    def loaded(self) -> list[str]:
        return list(self._loaded)

    @property
    def errors(self) -> list[str]:
        return list(self._errors)
