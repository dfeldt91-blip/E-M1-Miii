#!/usr/bin/env bash
# Build a universal (Apple silicon + Intel) "E-M1 III Mod Builder.app" on ANY Mac, including GitHub's
# Intel Macs (their Apple-silicon runners are often not available). Uses python.org's universal2
# Python and fuses the arm64 and x86_64 wheels of the two native dependencies (Pillow, lz4) with
# delocate-merge, then PyInstaller --target-arch universal2.
# Result: dist/E-M1 III Mod Builder.app and dist/E-M1-III-Mod-Builder-mac-universal.zip
set -euo pipefail
cd "$(dirname "$0")/../.."
PYVER=${PYVER:-3.12.10}
PY=/Library/Frameworks/Python.framework/Versions/3.12/bin/python3
if [ ! -x "$PY" ] || ! file "$PY" | grep -q arm64 || ! file "$PY" | grep -q x86_64; then
  curl -fsSL -o /tmp/python.pkg "https://www.python.org/ftp/python/$PYVER/python-$PYVER-macos11.pkg"
  sudo installer -pkg /tmp/python.pkg -target /
fi
"$PY" -m pip install --quiet --upgrade pip
"$PY" -m pip install --quiet --upgrade pyinstaller certifi delocate
rm -rf wheels && mkdir -p wheels/arm64 wheels/x86_64 wheels/fused
ARM="--platform macosx_11_0_arm64 --platform macosx_12_0_arm64 --platform macosx_13_0_arm64 --platform macosx_14_0_arm64"
X86="--platform macosx_10_9_x86_64 --platform macosx_10_13_x86_64 --platform macosx_10_15_x86_64 --platform macosx_11_0_x86_64 --platform macosx_12_0_x86_64"
for pkg in pillow lz4; do
  "$PY" -m pip download --quiet --only-binary=:all: --no-deps --python-version 3.12 $ARM -d wheels/arm64 "$pkg"
  "$PY" -m pip download --quiet --only-binary=:all: --no-deps --python-version 3.12 $X86 -d wheels/x86_64 "$pkg"
done
ls wheels/arm64 wheels/x86_64
for pkg in pillow lz4; do
  a=$(ls wheels/arm64/${pkg}-*.whl); x=$(ls wheels/x86_64/${pkg}-*.whl)
  "$(dirname "$PY")/delocate-merge" "$a" "$x" -w wheels/fused
done
ls wheels/fused
"$PY" -m pip install --quiet --force-reinstall --no-deps wheels/fused/*.whl
NAME="E-M1 III Mod Builder"
rm -rf build dist
"$PY" -m PyInstaller --noconfirm --windowed --name "$NAME" --target-arch universal2 \
  --osx-bundle-identifier io.github.em1iii.modbuilder \
  --paths tools \
  --hidden-import modcore --hidden-import olyfw --hidden-import olycompress --hidden-import patch_frame_white --hidden-import patch_xpan_icon --hidden-import patch_underwater_mono --hidden-import patch_looks --hidden-import looks_library --hidden-import patch_owner_title \
  --hidden-import lz4.block --hidden-import certifi --hidden-import PIL.Image --hidden-import PIL.ImageDraw --hidden-import PIL.ImageChops --hidden-import PIL.JpegImagePlugin \
  --add-data "builder/mods.json:." \
  builder/em1iii_builder.py
lipo -archs "dist/$NAME.app/Contents/MacOS/$NAME"
(cd dist && ditto -c -k --sequesterRsrc --keepParent "$NAME.app" E-M1-III-Mod-Builder-mac-universal.zip)
ls -la dist
