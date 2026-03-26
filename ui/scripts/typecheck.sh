#!/usr/bin/env bash
# Uses vue-tsc instead of plain tsc. Plain tsc cannot type-check inside .vue
# files, so it misses errors that VS Code (Volar) catches. vue-tsc uses the
# same Volar engine and produces identical results to VS Code's diagnostics.

cd "$(dirname "$0")/.." || exit 1
npx vue-tsc --noEmit "$@"
