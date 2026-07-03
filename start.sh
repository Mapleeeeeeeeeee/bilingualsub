#!/bin/bash

# Check if we should start CLIProxy (either secret variables are set, or the directory already contains files)
if [ -n "$CLIPROXY_ANTIGRAVITY_JSON" ] || [ -n "$CLIPROXY_CODEX_JSON" ]; then
  echo "CLIProxy credentials found. Initializing CLIProxy..."
  
  mkdir -p /tmp/.cli-proxy-api
  
  if [ -n "$CLIPROXY_ANTIGRAVITY_JSON" ]; then
    echo "$CLIPROXY_ANTIGRAVITY_JSON" > /tmp/.cli-proxy-api/antigravity-mapleee723@gmail.com.json
  fi
  if [ -n "$CLIPROXY_CODEX_JSON" ]; then
    echo "$CLIPROXY_CODEX_JSON" > /tmp/.cli-proxy-api/codex-acforgptonly@gmail.com-pro.json
  fi
  
  cat <<EOF > /tmp/cliproxyapi.yaml
host: "127.0.0.1"
port: 8317
auth-dir: "/tmp/.cli-proxy-api"
api-keys:
  - "bilingualsub-local"
debug: false
logging-to-file: false
usage-statistics-enabled: false
oauth-model-alias:
  antigravity:
    - name: "gemini-3.5-flash-low"
      alias: "bilingualsub-gemini-flash"
      fork: true
      force-mapping: true
EOF

  # Start CLIProxy in the background
  cliproxyapi -config /tmp/cliproxyapi.yaml &
  
  # Configure bilingualsub to use the local proxy
  export OPENAI_BASE_URL="http://127.0.0.1:8317/v1"
  export OPENAI_API_KEY="bilingualsub-local"
  export TRANSLATOR_MODEL="openai:bilingualsub-gemini-flash"
  echo "CLIProxy started. Routing translation requests through proxy."
else
  echo "No CLIProxy credentials provided. Running in direct API mode."
fi

# Run the FastAPI server
uv run uvicorn bilingualsub.api.app:app --host 0.0.0.0 --port 7860
