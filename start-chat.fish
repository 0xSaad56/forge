#!/usr/bin/env fish
set -l ROOT (cd (dirname (status -f)); and pwd)
cd $ROOT
if not test -x .venv/bin/python
    echo "Run ./install.fish first"; exit 1
end
set -x OMP_NUM_THREADS 4
set -x MKL_NUM_THREADS 4
set -x TOKENIZERS_PARALLELISM false
set -x ANONYMIZED_TELEMETRY False
set -x CHROMA_TELEMETRY_IMPLEMENTATION none
set -x POSTHOG_DISABLED 1
echo "Forge UI → http://127.0.0.1:8765"
echo "Need llama-server on :5000"
exec .venv/bin/python -m uvicorn server:app --host 127.0.0.1 --port 8765
