#!/usr/bin/env bash
set -euo pipefail

# Weekly TEASER-safe proof regeneration (deterministic)
# Output goes to /tmp and is safe to share as evidence paths.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

bash scripts/run_public_teaser_proofs.sh
