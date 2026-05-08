# -*- mode: python ; coding: utf-8 -*-

import os
import re
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH).parents[1]
APP_NAME = "CoView"
BUNDLE_ID = "com.miniyifan.coview"
ICON_FILE = ROOT / "app_icons" / "AppIcon.icns"


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

for package_name in ("sherpa_onnx", "sentencepiece"):
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
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
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

app = BUNDLE(
    coll,
    name=f"{APP_NAME}.app",
    icon=str(ICON_FILE) if ICON_FILE.exists() else None,
    bundle_identifier=BUNDLE_ID,
    info_plist={
        "CFBundleDisplayName": "CoView",
        "CFBundleName": "CoView",
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": VERSION,
        "LSApplicationCategoryType": "public.app-category.productivity",
        "NSAppleEventsUsageDescription": "CoView needs automation permission to help operate apps at your request.",
        "NSMicrophoneUsageDescription": "CoView uses the microphone for optional voice interaction and wake word detection.",
        "NSSpeechRecognitionUsageDescription": "CoView uses speech recognition when voice input is enabled.",
    },
)
