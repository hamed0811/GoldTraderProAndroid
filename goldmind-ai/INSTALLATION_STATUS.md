# GoldMind AI installation status

Installed from: syarief02/goldmind-ai
Target repository: hamed0811/GoldTraderProAndroid

This integration is isolated under goldmind-ai/ and does not overwrite the existing Android project.

Safety:
- A backup branch was created before integration.
- The original main project files remain intact.
- The upstream project contains MT5 order-execution logic. It must be converted to SIGNAL-ONLY before being used for the intended workflow.
- No live broker credentials or OpenAI API keys are stored in this repository.

Note: The upstream compiled .ex5 binary is not copied by this integration step because the available GitHub connector cannot safely transfer that binary blob. The backend and configuration files are included; the EA binary can be added later from the upstream repository when binary upload is available.
