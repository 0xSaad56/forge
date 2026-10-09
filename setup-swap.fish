#!/usr/bin/env fish
# Create 16GB swap so Qwen3-Embedding-4B + main model can coexist on 16GB RAM
# Safe to re-run: skips if swapfile already active

set -l SWAPFILE /swapfile
set -l SIZE_GB 16

if swapon --show | grep -q "$SWAPFILE"
    echo "Swap already active:"
    swapon --show
    free -h
    exit 0
end

echo "Creating {$SIZE_GB}G swap at $SWAPFILE (needs sudo)..."
sudo fallocate -l {$SIZE_GB}G $SWAPFILE
or sudo dd if=/dev/zero of=$SWAPFILE bs=1G count=$SIZE_GB status=progress

sudo chmod 600 $SWAPFILE
sudo mkswap $SWAPFILE
sudo swapon $SWAPFILE

if not grep -q "$SWAPFILE" /etc/fstab
    echo "$SWAPFILE none swap sw 0 0" | sudo tee -a /etc/fstab
end

echo "Done."
swapon --show
free -h
