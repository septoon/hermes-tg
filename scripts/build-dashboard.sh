#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
export PATH="$project_dir/.hermes/node/bin:$PATH"
cd "$project_dir/hermes-agent"
npm ci --workspace web --workspace ui-tui --ignore-scripts --no-audit --no-fund
npm run build --workspace web
npm run build --workspace ui-tui
