#!/usr/bin/env bash
# Build "E-M1 III Mod Builder.exe" with PyInstaller (run on Windows in Git Bash; the GitHub workflow
# .github/workflows/mac-app.yml runs this on GitHub's Windows machines).
# Result: dist/E-M1 III Mod Builder.exe and dist/E-M1-III-Mod-Builder-windows.zip
set -euo pipefail
cd "$(dirname "$0")/../.."
PY=${PYTHON:-python}
"$PY" -m pip install --quiet --upgrade pyinstaller lz4 certifi pillow
NAME="E-M1 III Mod Builder"
rm -rf build dist
"$PY" -m PyInstaller --noconfirm --windowed --onefile --name "$NAME" \
  --paths tools \
  --hidden-import modcore --hidden-import olyfw --hidden-import olycompress --hidden-import patch_frame_white --hidden-import patch_xpan_icon --hidden-import patch_underwater_mono --hidden-import patch_looks --hidden-import looks_library \
  --hidden-import lz4.block --hidden-import certifi --hidden-import PIL.Image --hidden-import PIL.ImageDraw --hidden-import PIL.ImageChops --hidden-import PIL.JpegImagePlugin \
  --add-data "builder/mods.json;." \
  builder/em1iii_builder.py
(cd dist && "$PY" -c "import zipfile; z = zipfile.ZipFile('E-M1-III-Mod-Builder-windows.zip', 'w', zipfile.ZIP_DEFLATED); z.write('$NAME.exe'); z.close()")
ls -la dist
