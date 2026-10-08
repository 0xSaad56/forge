#!/usr/bin/env fish
set -l MODEL_DIR "$HOME/models/Huihui-Qwen3-8B-abliterated-v2-Q4_K_M"
set -l MODEL "$MODEL_DIR/Huihui-Qwen3-8B-abliterated-v2.Q4_K_M.gguf"
if not test -s "$MODEL"
    for f in $MODEL_DIR/*.gguf
        if test -s "$f"; set MODEL "$f"; break; end
    end
end
if not command -q llama-server
    echo "llama-server missing — sudo pacman -S llama-cpp"; exit 1
end
if not test -s "$MODEL"
    echo "GGUF not found in $MODEL_DIR"; exit 1
end
echo "Forge model → $MODEL"
exec llama-server -m "$MODEL" --host 127.0.0.1 --port 5000 -ngl 99 -c 20480 -np 1 -fa on --cache-type-k q8_0 --cache-type-v q4_0 --threads 8 --offline --metrics
