#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
export HERMES_HOME="$project_dir/.hermes"
umask 077
cd "$project_dir"
git config core.hooksPath .githooks
git submodule update --init --depth 1
mkdir -p "$HERMES_HOME"
chmod 700 "$HERMES_HOME"
if [[ ! -f .env ]]; then
  cp .env.example .env
fi
chmod 600 .env
if [[ ! -e "$HERMES_HOME/.env" && ! -L "$HERMES_HOME/.env" ]]; then
  ln -s ../.env "$HERMES_HOME/.env"
fi
if [[ ! -f "$HERMES_HOME/config.yaml" ]]; then
  cp config.yaml "$HERMES_HOME/config.yaml"
fi
bash hermes-agent/scripts/install.sh --dir "$project_dir/hermes-agent" \
  --stage prerequisites --non-interactive --skip-browser --skip-computer-use --skip-setup
cd hermes-agent
UV_PROJECT_ENVIRONMENT="$PWD/venv" "$HERMES_HOME/bin/uv" sync \
  --locked --no-dev --extra messaging --extra web --extra pty --python 3.13
cd "$project_dir"
mkdir -p "$HERMES_HOME/plugins"
ln -sfn ../../plugins/telegram-auth "$HERMES_HOME/plugins/telegram-auth"
"$project_dir/hermes" plugins enable telegram-auth
mkdir -p "$HOME/.local/bin"
if [[ ! -e "$HOME/.local/bin/hermes" && ! -L "$HOME/.local/bin/hermes" ]]; then
  printf '#!/usr/bin/env bash\nexec %q "$@"\n' "$project_dir/hermes" > "$HOME/.local/bin/hermes"
  chmod 755 "$HOME/.local/bin/hermes"
fi
"$project_dir/hermes" config migrate
"$project_dir/hermes" --version
