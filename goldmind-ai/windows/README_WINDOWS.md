# GoldTrader Pro — Windows

Native Windows signal terminal for the existing GoldMind backend.

## AI connection — OmniRoute first

The Windows build uses OmniRoute as its default OpenAI-compatible gateway:

- Base URL: `http://localhost:20128/v1`
- Model: `auto` by default
- The actual free provider is selected inside OmniRoute.
- No OpenAI paid API is required when a free OmniRoute provider is connected.

OmniRoute currently documents free options including Kiro AI, OpenCode Free, and Pollinations. citeturn0search0turn0search1

Create `.env` beside the EXE:

```
AI_BASE_URL=http://localhost:20128/v1
OMNIROUTE_API_KEY=YOUR_OMNIROUTE_KEY
AI_MODEL=auto
```

The OmniRoute key is the local gateway key shown by OmniRoute; it is not an OpenAI provider key.

## Start order

1. Start OmniRoute on Windows.
2. Connect at least one free provider in the OmniRoute dashboard.
3. Start `GoldTraderPro-Windows-x64.exe`.
4. The terminal starts the GoldMind server on `127.0.0.1:8000`.
5. MT5 sends market data to GoldMind; the AI request is routed through OmniRoute.

OmniRoute's documented API endpoint is `http://localhost:20128/v1`. citeturn0search0turn0search8

## Safety

- Signal-only.
- No order placement, modification, cancellation, or position management.
- No credentials are embedded into the EXE.
- If AI is unavailable, the backend returns WAIT rather than inventing a signal.

## Build from source

```
python -m pip install -r goldmind-ai/windows/requirements-windows.txt
python goldmind-ai/windows/windows_app.py
```
