#!/usr/bin/env bash
# Copia señales AIS11 a la VM Oracle. No usa git (los JSON están gitignored).
# Uso:
#   OCI_HOST=... OCI_USER=ubuntu OCI_DIR='$HOME/IABacktesterTrading-Nazareno' \
#     bash scripts/export_ai_signals_for_oracle.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST="${OCI_HOST:?Set OCI_HOST}"
USER="${OCI_USER:-ubuntu}"
PORT="${OCI_PORT:-22}"
DEST_DIR="${OCI_DIR:-\$HOME/IABacktesterTrading-Nazareno}"

FILES=(
  timesfm_signals.json
  tspulse_signals.json
  minirocket_gpu_signals.json
)

for f in "${FILES[@]}"; do
  src="$ROOT/data/$f"
  if [ ! -f "$src" ]; then
    echo "Falta $src — genera IA local con actualizar_ia_live_us.bat"
    exit 1
  fi
  echo "→ $USER@$HOST:$DEST_DIR/data/$f"
  scp -P "$PORT" "$src" "$USER@$HOST:$DEST_DIR/data/$f"
done

echo "OK. En la VM: sudo systemctl restart backtester"
echo "Luego /salud en Telegram para ver % NO_AI."
