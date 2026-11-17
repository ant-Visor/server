import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class ModuleInfo:
  id: str
  name: str
  description: str
  required: bool = False


MODULE_METADATA = {
  "base": ModuleInfo("base", "Base", "Основные команды userbot", required=True),
  "spaceTW": ModuleInfo("spaceTW", "SpaceTW", "Игровой модуль и бот уведомлений"),
}


def list_modules(catalog_dir: Path, allowed_ids: frozenset[str] | set[str] | None = None) -> list[dict]:
  modules = []
  if not catalog_dir.is_dir():
    return modules

  for module_path in sorted(catalog_dir.iterdir(), key=lambda item: item.name.casefold()):
    if not module_path.is_dir():
      continue
    if allowed_ids is not None and module_path.name not in allowed_ids:
      continue

    releases = []
    for release_path in module_path.iterdir():
      if not release_path.is_dir() or not (release_path / "__init__.py").is_file():
        continue
      manifest_path = release_path / "module.json"
      try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        version = str(manifest.get("version", release_path.name))
        match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", version)
        if not match or version.removeprefix("v") != release_path.name.removeprefix("v"):
          continue
      except (OSError, json.JSONDecodeError):
        continue
      releases.append((tuple(map(int, match.groups())), release_path, manifest, version))

    if not releases:
      continue
    _, _, manifest, version = max(releases, key=lambda item: item[0])
    defaults = MODULE_METADATA.get(module_path.name)
    modules.append({
      "id": module_path.name,
      "name": manifest.get("name", defaults.name if defaults else module_path.name),
      "description": manifest.get("description", defaults.description if defaults else ""),
      "required": bool(manifest.get("required", defaults.required if defaults else False)),
      "version": version,
    })
  return modules


def validate_selection(
  catalog_dir: Path,
  selected: list[str],
  allowed_ids: frozenset[str] | set[str] | None = None,
) -> list[str]:
  available = {module["id"] for module in list_modules(catalog_dir, allowed_ids)}
  selection = list(dict.fromkeys(selected))
  if "base" not in selection:
    selection.insert(0, "base")
  unknown = set(selection) - available
  if unknown:
    raise ValueError(f"Unknown module(s): {', '.join(sorted(unknown))}")
  return selection
