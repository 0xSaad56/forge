#!/usr/bin/env fish
set -l MODEL_DIR "$HOME/models/Huihui-Qwen3-8B-abliterated-v2-Q4_K_M"
set -l MODEL ""
for f in $MODEL_DIR/*.gguf
    if test -s "$f"; set MODEL "$f"; break; end
end
if not command -q llama-server
    echo "Install llama-server: sudo pacman -S llama-cpp"; exit 1
end
if test -z "$MODEL"
    echo "No GGUF found in $MODEL_DIR"; exit 1
end
echo "Forge LLM → $MODEL"
echo "Listening  → http://127.0.0.1:5000"
exec llama-server -m "$MODEL" --host 127.0.0.1 --port 5000 \
    -ngl 99 -c 20480 -np 1 -fa on \
    --cache-type-k q8_0 --cache-type-v q4_0 \
    --threads 8 --offline --metrics
