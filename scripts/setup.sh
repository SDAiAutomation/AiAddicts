#!/usr/bin/env bash
# FI Validator — environment setup
set -euo pipefail

echo "=== FI Validator — Setup ==="

# 1. Create project directories
mkdir -p data/fi_samples data/chroma_db

# 2. Python dependencies
echo ""
echo "--- Installing Python dependencies ---"
pip install -r requirements.txt

# 3. Ollama
echo ""
echo "--- Checking Ollama ---"
if ! command -v ollama &>/dev/null; then
    echo "Ollama not found. Installing..."
    curl -fsSL https://ollama.com/install.sh | sh
else
    echo "Ollama already installed: $(ollama --version)"
fi

# 4. Pull models
echo ""
echo "--- Pulling Ollama models ---"
ollama pull mistral
ollama pull nomic-embed-text

echo ""
echo "--- Verifying models ---"
ollama list

# 5. Copy env file
if [ ! -f .env ]; then
    cp .env.example .env
    echo ""
    echo "Created .env from .env.example — edit it if needed."
fi

echo ""
echo "=== Setup complete ==="
echo ""
echo "Next steps:"
echo "  1. Start Ollama:          ollama serve"
echo "  2. Index sample FIs:      python scripts/ingest_documents.py --dir data/fi_samples"
echo "  3. Launch the app:        streamlit run app.py"
