# GoldMind AI — installation status

Target: hamed0811/GoldTraderProAndroid  
Upstream reference: syarief02/goldmind-ai

## Current state

- Backend integrated under `goldmind-ai/backend/`.
- A dedicated MT5 source EA is now in `goldmind-ai/mt5/Experts/GoldMind_AI_SIGNAL_ONLY.mq5`.
- The MT5 EA is **SIGNAL-ONLY**: it reads live XAUUSD/GOLD data, requests analysis, and displays BUY/SELL/WAIT plus Entry/SL/TP. It does not contain order-placement, modification, cancellation, or position-management calls.
- The backend is hardened for XAUUSD/GOLD only and returns WAIT on insufficient data, unavailable ATR, excessive spread, or invalid model geometry.
- The target horizon is short-horizon analysis (normally around 10 minutes); signal quality is preferred over signal frequency.
- The old upstream `.ex5` remains only as an upstream reference. It must not be used for this signal-only build because the upstream EA contains automatic order execution.
- `INSTALL_MT5_SIGNAL_ONLY.cmd` installs the source EA into the user's MT5 Data Folder on Windows.
- No broker credentials or OpenAI API keys are stored in GitHub.
- Backup branch created before signal-only changes: `backup-before-signal-only-20261008`.
- Earlier integration backup remains: `backup-before-goldmind-ai`.

## Required local step

GitHub can store and deliver the MT5 source, but it cannot run MetaTrader 5 or MetaEditor on the user's PC. After the CMD installer is run on Windows, MetaEditor must compile the EA and report **0 errors**. That local compilation is the remaining environment-dependent verification.

## Safety rule

Do not enable or attach the old `GoldMind_AI.ex5` execution EA for this project. Use only `GoldMind_AI_SIGNAL_ONLY.mq5`.
