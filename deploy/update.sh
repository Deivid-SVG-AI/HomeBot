#!/usr/bin/env bash
# Actualiza Búho: trae los cambios de GitHub y reinstala lo necesario.
# Uso, como tu usuario (no root), en la Pi:   /opt/buho/deploy/update.sh
set -euo pipefail

cd "$(dirname "$0")/.."
git pull --ff-only
sudo ./deploy/install_pi.sh
