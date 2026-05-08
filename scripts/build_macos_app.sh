#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

APP_NAME="CoView"
SPEC_FILE="$ROOT_DIR/packaging/macos/CoView.spec"
VENV_DIR="${VENV_DIR:-$ROOT_DIR/.venv}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
SKIP_INSTALL="${SKIP_INSTALL:-0}"
SKIP_MODEL_DOWNLOAD="${SKIP_MODEL_DOWNLOAD:-0}"
CREATE_DMG="${CREATE_DMG:-1}"
CLEAN_BUILD="${CLEAN_BUILD:-1}"
CODESIGN_IDENTITY="${CODESIGN_IDENTITY:-}"
BUILD_DIR="$ROOT_DIR/build"
DIST_DIR="$ROOT_DIR/dist"

log() {
  printf '\033[1;34m==>\033[0m %s\n' "$1"
}

fail() {
  printf '\033[1;31merror:\033[0m %s\n' "$1" >&2
  exit 1
}

require_macos() {
  [[ "$(uname -s)" == "Darwin" ]] || fail "macOS app packages must be built on macOS."
}

version() {
  "$VENV_DIR/bin/python" - <<'PY'
from baodou_ai import __version__
print(__version__)
PY
}

require_macos

if [[ ! -d "$VENV_DIR" ]]; then
  log "Creating virtual environment at $VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

log "Using Python: $("$VENV_DIR/bin/python" --version)"

if [[ "$SKIP_INSTALL" != "1" ]]; then
  log "Installing build dependencies"
  "$VENV_DIR/bin/python" -m pip install --upgrade pip
  "$VENV_DIR/bin/python" -m pip install -e ".[build,voice,tts,macos]"
else
  log "Skipping dependency install because SKIP_INSTALL=1"
fi

if [[ "$SKIP_MODEL_DOWNLOAD" != "1" ]]; then
  log "Ensuring bundled wake word model exists"
  "$VENV_DIR/bin/python" scripts/download_wake_word_model.py
else
  log "Skipping wake word model download because SKIP_MODEL_DOWNLOAD=1"
fi

APP_VERSION="$(version)"
export COVIEW_VERSION="$APP_VERSION"
log "Building $APP_NAME $APP_VERSION with PyInstaller"

PYINSTALLER_ARGS=("$SPEC_FILE" "--noconfirm" "--distpath" "$DIST_DIR" "--workpath" "$BUILD_DIR")
if [[ "$CLEAN_BUILD" == "1" ]]; then
  PYINSTALLER_ARGS+=("--clean")
fi

"$VENV_DIR/bin/pyinstaller" "${PYINSTALLER_ARGS[@]}"

APP_PATH="$DIST_DIR/$APP_NAME.app"
[[ -d "$APP_PATH" ]] || fail "Expected app bundle was not created: $APP_PATH"

AEC_LIB_SOURCE="$("$VENV_DIR/bin/python" - <<'PY'
from pathlib import Path

try:
    import aec_audio_processing
except Exception:
    raise SystemExit(0)

package_dir = Path(aec_audio_processing.__file__).resolve().parent
for name in ("libwebrtc-audio-processing-2.1.dylib", "libwebrtc-audio-processing-2.dylib"):
    candidate = package_dir / "files" / name
    if candidate.exists():
        print(candidate)
        break
PY
)"
if [[ -n "$AEC_LIB_SOURCE" ]]; then
  AEC_LIB_TARGET="$APP_PATH/Contents/Frameworks/libwebrtc-audio-processing-2.1.dylib"
  log "Bundling WebRTC AEC library"
  cp "$AEC_LIB_SOURCE" "$AEC_LIB_TARGET"
  install_name_tool -id "@rpath/libwebrtc-audio-processing-2.1.dylib" "$AEC_LIB_TARGET" || true
  codesign --force --sign - "$AEC_LIB_TARGET" >/dev/null 2>&1 || true
fi

if [[ -n "$CODESIGN_IDENTITY" ]]; then
  log "Signing app bundle with identity: $CODESIGN_IDENTITY"
  codesign --force --deep --options runtime --timestamp --sign "$CODESIGN_IDENTITY" "$APP_PATH"
else
  log "Ad-hoc signing app bundle"
  codesign --force --deep --sign - "$APP_PATH"
fi

if [[ "$CREATE_DMG" == "1" ]]; then
  DMG_PATH="$DIST_DIR/${APP_NAME}-${APP_VERSION}-macOS.dmg"
  ZIP_PATH="$DIST_DIR/${APP_NAME}-${APP_VERSION}-macOS.zip"
  log "Creating DMG: $DMG_PATH"
  rm -f "$DMG_PATH"
  if hdiutil create -volname "$APP_NAME" -srcfolder "$APP_PATH" -ov -format UDZO "$DMG_PATH"; then
    log "Done: $DMG_PATH"
  else
    log "DMG creation failed; creating ZIP fallback: $ZIP_PATH"
    ditto -c -k --keepParent "$APP_PATH" "$ZIP_PATH"
    log "Done: $ZIP_PATH"
  fi
else
  log "Skipping DMG creation because CREATE_DMG=0"
  log "Done: $APP_PATH"
fi
