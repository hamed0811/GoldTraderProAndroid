# Freestyle.sh VM integration (staging branch)

Status: **integration scaffold only — no VM has been provisioned yet**.

This repository's Android app is a signal-only client and its existing FastAPI service lives in `goldmind-ai/backend`. Freestyle can host a persistent Linux VM for that backend, but provisioning requires an owner-controlled Freestyle account/API key and review of the account's current usage limits.

## Safety and deployment design

- Keep the Android APK as a client; do not put Freestyle, MT5, or AI-provider secrets in Android resources.
- Store `FREESTYLE_API_KEY` only in the Freestyle/CI secret store. Never commit it to Git, a workflow file, or `.env.example`.
- Keep order entry disabled. Deploy the existing signal-only backend first; do not enable live trading as part of hosting setup.
- Configure the VM firewall explicitly. Do not expose the backend publicly until authentication, TLS, and allowed ingress are verified.
- Do not report the service as live until a real VM, health check, and external reachability test succeed.

## Account setup (owner action required)

1. Create/sign in to an account at https://dash.freestyle.sh/.
2. Review current pricing/usage and free allowances at https://www.freestyle.sh/pricing before provisioning.
3. Create an API key following https://www.freestyle.sh/docs/cli. Treat it as a password; do not paste it into a GitHub issue or commit.
4. In GitHub, open **Settings → Secrets and variables → Actions** and add repository secret `FREESTYLE_API_KEY` only if a CI workflow will use it.
5. Provision a staging VM using the official CLI, then verify the VM status, firewall, and app health before considering a production deployment.

## Local CLI check

Install Node.js 20+ on the Windows/PowerShell machine, then run:

```powershell
npx freestyle@latest --help
npx freestyle@latest login
npx freestyle@latest whoami
npx freestyle@latest vm list
```

These commands inspect/authenticate the account; they do not create a VM. Create a VM only after reviewing pricing and choosing the intended region/resources. The official CLI guide documents `vm create`, `vm exec`, and lifecycle commands: https://www.freestyle.sh/docs/cli.

## Acceptance checklist

- [ ] Freestyle account and usage limits confirmed by owner
- [ ] Staging VM provisioned (record VM ID/slug; never record API key)
- [ ] Backend deployed from this repository's reviewed commit
- [ ] Firewall permits only intended traffic
- [ ] HTTPS and authentication verified before public exposure
- [ ] Health endpoint and WebSocket tested with real responses
- [ ] NO DATA / WAIT behavior retained when market data is missing or stale
- [ ] No exchange keys or trading secrets shipped to Android
- [ ] Costs and shutdown/pause behavior documented

Until these checks pass, the Android app must continue to show the server as unconfigured/unavailable rather than implying that Freestyle is running.
