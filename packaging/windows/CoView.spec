# -*- mode: python ; coding: utf-8 -*-

import os
import re
from importlib.util import find_spec
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH).parents[1]
APP_NAME = "CoView"
ICON_FILE = ROOT / "app_icons" / "AppIcon.ico"


def read_version() -> str:
    version_override = os.environ.get("COVIEW_VERSION", "").strip()
    if version_override:
        return version_override
    init_text = (ROOT / "src" / "baodou_ai" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*"([^"]+)"', init_text)
    return match.group(1) if match else "0.0.0"


VERSION = read_version()


datas = [
    (str(ROOT / "defaultgif.gif"), "."),
    (str(ROOT / "src" / "baodou_ai" / "ai" / "prompts"), "baodou_ai/ai/prompts"),
]
binaries = []
hiddenimports = ["PyQt5.sip"]

model_dir = ROOT / "models"
if model_dir.exists():
    datas.append((str(model_dir), "models"))

for package_name in ("sherpa_onnx", "sentencepiece", "aec_audio_processing"):
    if find_spec(package_name) is None:
        continue
    package_datas, package_binaries, package_hiddenimports = collect_all(package_name)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hiddenimports


a = Analysis(
    [str(ROOT / "src" / "baodou_ai" / "__main__.py")],
    pathex=[str(ROOT / "src"), str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=str(ICON_FILE) if ICON_FILE.exists() else None,
    version=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=APP_NAME,
)
