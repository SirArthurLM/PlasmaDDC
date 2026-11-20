#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python"
APP_FILE="$SCRIPT_DIR/app.py"

cd "$SCRIPT_DIR"

if [[ ! -x "$VENV_PYTHON" ]]; then
    echo "No existe el entorno virtual de PlasmaDDC:"
    echo "  $SCRIPT_DIR/.venv"
    echo
    echo "Ejecuta primero:"
    echo "  ./install_plasmaddc.sh"
    echo
    echo "O crea el entorno manualmente:"
    echo "  python3 -m venv .venv"
    echo "  source .venv/bin/activate"
    echo "  pip install -r requirements.txt"
    exit 1
fi

if [[ ! -f "$APP_FILE" ]]; then
    echo "No se encuentra app.py en:"
    echo "  $SCRIPT_DIR"
    exit 1
fi

exec "$VENV_PYTHON" "$APP_FILE" "$@"
