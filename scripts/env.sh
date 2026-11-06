# Source this file: `source scripts/env.sh`. No secrets.
if [ -n "${BASH_SOURCE[0]:-}" ]; then _kl_src="${BASH_SOURCE[0]}"; else _kl_src="${(%):-%x}"; fi
KRONOS_LAB_ROOT="$(cd "$(dirname "$_kl_src")/.." && pwd)"
unset _kl_src
export KRONOS_LAB_ROOT
export HF_HOME="$KRONOS_LAB_ROOT/.cache/huggingface"
export HF_HUB_CACHE="$KRONOS_LAB_ROOT/.cache/huggingface/hub"
export TORCH_HOME="$KRONOS_LAB_ROOT/.cache/torch"
export PIP_CACHE_DIR="$KRONOS_LAB_ROOT/.cache/pip"
export XDG_CACHE_HOME="$KRONOS_LAB_ROOT/.cache/xdg"
export MPLCONFIGDIR="$KRONOS_LAB_ROOT/.cache/matplotlib"
export HF_HUB_DISABLE_TELEMETRY=1
