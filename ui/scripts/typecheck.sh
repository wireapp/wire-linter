#!/usr/bin/env bash
# Runs the TypeScript compiler against tsconfig.app.json, which is the config
# VS Code actually uses for source files. The root tsconfig.json has "files": []
# and only contains project references, so plain "npx tsc --noEmit" reports
# zero errors even when real issues exist.

cd "$(dirname "$0")/.." || exit 1
npx tsc --noEmit -p tsconfig.app.json "$@"
