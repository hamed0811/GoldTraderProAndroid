# GoldMind AI installation status

Installed from: syarief02/goldmind-ai
Target repository: hamed0811/GoldTraderProAndroid

This integration is isolated under goldmind-ai/ and does not overwrite the existing Android project.

Safety:
- A backup branch was created before integration.
- The original main project files remain intact.
- The upstream project contains MT5 order-execution logic. It must be converted to SIGNAL-ONLY before being used for the intended workflow.
- No live broker credentials or OpenAI API keys are stored in this repository.

The upstream compiled .ex5 binary remains in the original GoldMind AI repository. Because the GitHub connector cannot read/re-upload binary blobs directly, INSTALL_MT5_FULL.cmd was added to download the exact upstream binary and JASONNode.mqh directly to a Windows MT5 Data Folder. This completes the repository-side installation package; running that CMD file on Windows completes the local MT5 installation.
