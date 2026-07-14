"""从用户本机 Rain World 安装提取图集到 ~/.slugcatpet/assets。"""
from __future__ import annotations
import re
import sys
from pathlib import Path

from ._paths import assets_dir, bundled_assets_dir
from .i18n import t

# 图集名：base + MSC 各含贴图与 UI
ATLASES = ("rainWorld", "rainworldmsc",
           "uiSprites", "uispritesmsc")
_ATLAS_REL = Path("RainWorld_Data") / "resources.assets"


class SetupError(RuntimeError):
    """导入失败，message 面向用户、可照做。"""


def atlases_present(d: Path) -> bool:
    return all((d / f).exists() for f in
               ("rainWorld", "rainWorld.png", "rainworldmsc", "rainworldmsc.png",
                "uiSprites", "uiSprites.png", "uispritesmsc", "uispritesmsc.png"))


# 定位 Steam 安装

def _drive_roots() -> list[Path]:
    if sys.platform == "win32":
        return [Path(f"{c}:\\") for c in "CDEFGHIJKLMNOP"
                if Path(f"{c}:\\").exists()]
    # mac / linux Steam 默认库
    home = Path.home()
    return [home / "Library/Application Support/Steam",
            home / ".steam/steam", home / ".local/share/Steam"]


def _steam_root() -> Path | None:
    if sys.platform == "win32":
        try:
            import winreg
            for hive, key, val in (
                (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
            ):
                try:
                    with winreg.OpenKey(hive, key) as k:
                        p = Path(winreg.QueryValueEx(k, val)[0])
                        if p.exists():
                            return p
                except OSError:
                    pass
        except Exception:
            pass
    return None


def _steam_libraries() -> list[Path]:
    """枚举所有 Steam 库根目录。"""
    roots: list[Path] = []
    sr = _steam_root()
    if sr:
        roots.append(sr)
    for d in _drive_roots():
        roots += [d / "Program Files (x86)" / "Steam", d / "Steam",
                  d / "SteamLibrary", d]
    libs: list[Path] = []
    seen: set[Path] = set()
    for r in roots:
        if r in seen or not r.exists():
            continue
        seen.add(r)
        libs.append(r)
        vdf = r / "steamapps" / "libraryfolders.vdf"
        if vdf.exists():
            txt = vdf.read_text(encoding="utf-8", errors="ignore")
            for m in re.finditer(r'"path"\s*"([^"]+)"', txt):
                p = Path(m.group(1).replace("\\\\", "\\"))
                if p not in seen and p.exists():
                    seen.add(p)
                    libs.append(p)
    return libs


def detect_install() -> Path | None:
    """返回 Rain World 游戏根目录，找不到返回 None。"""
    for lib in _steam_libraries():
        game = lib / "steamapps" / "common" / "Rain World"
        if (game / _ATLAS_REL).exists():
            return game
    return None


# 提取

def extract_atlases(install: Path, dest: Path | None = None) -> Path:
    """从游戏 resources.assets 提取 4 个图集文件到 dest（默认 ~/.slugcatpet/assets）。"""
    install = Path(install)
    res = install / _ATLAS_REL
    if not res.exists():
        raise SetupError(t("err_atlas_missing", res=res))
    try:
        import UnityPy
    except ImportError as e:
        raise SetupError(t("err_no_unitypy")) from e

    dest = Path(dest or assets_dir())
    dest.mkdir(parents=True, exist_ok=True)
    want = set(ATLASES)
    got: dict[str, set[str]] = {}
    env = UnityPy.load(str(res))
    for obj in env.objects:
        if obj.type.name not in ("Texture2D", "TextAsset"):
            continue
        d = obj.read()
        name = getattr(d, "m_Name", None) or getattr(d, "name", None)
        if name not in want:
            continue
        if obj.type.name == "Texture2D":
            d.image.save(str(dest / f"{name}.png"))
            got.setdefault(name, set()).add("png")
        else:
            raw = d.m_Script if hasattr(d, "m_Script") else d.script
            if isinstance(raw, str):
                raw = raw.encode("utf-8", "surrogateescape")
            (dest / name).write_bytes(raw)
            got.setdefault(name, set()).add("map")

    if got.get("rainWorld") != {"png", "map"}:
        raise SetupError(t("err_base_fail"))
    if got.get("rainworldmsc") != {"png", "map"}:
        raise SetupError(t("err_msc_missing"))
    if got.get("uiSprites") != {"png", "map"}:
        raise SetupError(t("err_ui_fail"))
    if got.get("uispritesmsc") != {"png", "map"}:
        raise SetupError(t("err_uimsc_missing"))
    return dest


def ensure_atlases() -> Path:
    """已导入则直接返回，否则自动定位安装并提取。"""
    for d in (assets_dir(), bundled_assets_dir()):
        if atlases_present(d):
            return d
    install = detect_install()
    if not install:
        raise SetupError(t("err_no_install"))
    return extract_atlases(install)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    install = Path(argv[0]) if argv else detect_install()
    if install is None:
        print("未找到 Rain World 安装。用法：python -m slugcatpet.gameassets <游戏根目录>")
        return 2
    try:
        dest = extract_atlases(install)
    except SetupError as e:
        print(f"导入失败：{e}")
        return 1
    print(f"已从 {install} 导入图集到 {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
