#!/usr/bin/env fish
set -l ROOT (cd (dirname (status -f)); and pwd)
cd $ROOT
echo "=== Forge 2.1 install ==="

if command -q pacman
    sudo pacman -S --needed --noconfirm python python-pip python-virtualenv curl git base-devel
    sudo pacman -S --needed --noconfirm llama-cpp 2>/dev/null; or true
    sudo pacman -S --needed --noconfirm ggml-cuda 2>/dev/null; or true
end

if not test -x .venv/bin/python
    python3 -m venv .venv
    or begin; echo "venv failed"; exit 1; end
end

.venv/bin/pip install -U pip setuptools wheel
.venv/bin/pip install -r requirements.txt
or begin; echo "dependency install failed"; exit 1; end

set -l HAS_CUDA 0
if test -e /opt/cuda/lib64/libcudart.so; or test -e /usr/lib/libcudart.so; or test -e /usr/lib64/libcudart.so
    set HAS_CUDA 1
end
if test $HAS_CUDA -eq 1
    echo "CUDA runtime found — trying onnxruntime-gpu for faster ingest"
    .venv/bin/pip uninstall -y onnxruntime onnxruntime-gpu 2>/dev/null; or true
    .venv/bin/pip install "onnxruntime-gpu==1.30.0"
    or begin
        echo "GPU ORT failed; restoring CPU onnxruntime"
        .venv/bin/pip install "onnxruntime>=1.19.0"
    end
end

mkdir -p knowledge/{writeups,methodology,tools,cves,notes,intel} chroma chats data $HOME/models/forge-embedding
chmod 700 knowledge chroma chats data 2>/dev/null; or true

.venv/bin/python doctor.py
or echo "doctor reported issues (see above)"

echo ""
echo "Install complete."
echo "  1) GGUF model under ~/models/Huihui-Qwen3-8B-abliterated-v2-Q4_K_M/"
echo "  2) Optional: fish scripts/fetch-nvd-year.fish 2025"
echo "  3) .venv/bin/python ingest.py --force --device cuda"
echo "  4) ./start-llama.fish   then   ./start-chat.fish"
echo "  UI: http://127.0.0.1:8765"
