# GoldTrader Pro Android

Native Android client for real XAUUSD monitoring and minute-level signal alerts.

## Safety boundary
- **Order Entry is disabled.** This client does not place trades.
- MT5 credentials and AI provider keys never belong in the Android app.
- No synthetic price, PnL, confidence, candle or signal is generated when server data is missing.
- Missing/stale data is shown as NO DATA / WAIT.
- Smart Protection is OFF by default and remains server-side.

## Server
HTTP: http://SERVER_IP:8765
WebSocket: ws://SERVER_IP:8765/ws
Reads /api/state and consumes /ws; polling fallback is every 5 seconds.

## Figma
https://www.figma.com/design/P3Q4jDFPRfEqlZra6IyH7E

## Build
GitHub Actions builds a debug APK on push to android/** or manually via Actions → Android APK → Run workflow.
