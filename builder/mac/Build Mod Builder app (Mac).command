#!/usr/bin/env bash
# Double-click on a Mac to build "E-M1 III Mod Builder.app" yourself (universal: runs natively on Apple
# silicon and Intel). Needs an internet connection; installs python.org's Python 3.12 if it is missing
# (asks for your Mac password). The app ends up in the "dist" folder next to "builder".
cd "$(dirname "$0")/../.."
bash builder/mac/build_universal.sh && open dist
echo
read -r -p "Done. Press Return to close this window."
