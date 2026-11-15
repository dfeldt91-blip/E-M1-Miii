#!/usr/bin/env bash
# Build "E-M1 III Mod Builder.app" with PyInstaller (run on a Mac; the GitHub workflow
# .github/workflows/mac-app.yml runs this on GitHub's macOS machines).
# Result: dist/E-M1 III Mod Builder.app and dist/E-M1-III-Mod-Builder-mac.zip
set -euo pipefail
cd "$(dirname "$0")/../.."
PY=${PYTHON:-python3}
"$PY" -m pip install --quiet --upgrade pyinstaller lz4 certifi pillow
NAME="E-M1 III Mod Builder"
rm -rf build dist
"$PY" -m PyInstaller --noconfirm --windowed --name "$NAME" \
  --osx-bundle-identifier io.github.em1iii.modbuilder \
  --paths tools \
  --hidden-import modcore --hidden-import olyfw --hidden-import olycompress --hidden-import patch_frame_white --hidden-import patch_xpan_icon \
  --hidden-import lz4.block --hidden-import certifi --hidden-import PIL.Image --hidden-import PIL.ImageDraw --hidden-import PIL.ImageChops --hidden-import PIL.JpegImagePlugin \
  --add-data "builder/mods.json:." \
  builder/em1iii_builder.py
if [ "$(uname)" = Darwin ]; then
  (cd dist && ditto -c -k --sequesterRsrc --keepParent "$NAME.app" E-M1-III-Mod-Builder-mac.zip)
fi
ls -la dist
