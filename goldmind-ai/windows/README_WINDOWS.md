# GoldTrader Pro — Windows

Native Windows launcher for the existing GoldMind signal backend.

- Signal-only: no order placement, modification, cancellation, or position management.
- MT5 remains the market-data source.
- Android remains supported separately.
- Secrets are never embedded in GitHub or the EXE.

For a packaged EXE, keep a .env file beside the EXE:
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-5.2
FALLBACK_MODEL=gpt-5

Source run:
python -m pip install -r goldmind-ai/windows/requirements-windows.txt
python goldmind-ai/windows/windows_app.py

Local server: http://127.0.0.1:8000
