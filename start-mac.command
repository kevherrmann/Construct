#!/bin/bash
# Doppelklick-Starter für macOS. Öffnet ein Terminal und startet CONSTRUCT.
# (Der Finder führt .command-Dateien aus, .sh dagegen nicht.)
cd "$(dirname "$0")" || exit 1
exec ./start.sh "$@"
