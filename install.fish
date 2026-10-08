#!/usr/bin/env fish
set -l ROOT (dirname (status -f))
cd $ROOT
echo "=== Forge install ==="
if command -q pacman
    sudo pacman -S --needed --noconfirm python python-pip python-virtualenv curl git base-devel
    sudo pacman -S --needed --noconfirm llama-cpp 2>/dev/null
    sudo pacman -S --needed --noconfirm ggml-cuda 2>/dev/null
end
test -d .venv; or python -m venv .venv
.venv/bin/pip install -U pip
.venv/bin/pip install -r requirements.txt
mkdir -p knowledge/{writeups,methodology,tools,cves,notes} chroma chats data $HOME/models
echo "Done. Start: ./start-llama.fish && ./start-chat.fish"
