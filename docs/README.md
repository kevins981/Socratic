# Troubleshooting

### Codex Node version error
Symptoms:
```bash
$ sudo npm install -g @openai/codex
npm WARN notsup Unsupported engine for @openai/codex@0.77.0: wanted: {"node":">=16"} (current: {"node":"10.19.0","npm":"6.14.4"})
```
```bash
$ codex
/usr/local/lib/node_modules/@openai/codex/bin/codex.js:4
import { spawn } from "node:child_process";
```
Fix: Follow this to update node version: https://nodejs.org/en/download#debian-and-ubuntu-based-linux-distributions-enterprise-linux-fedora-and-snap-packages

### Landlock problems
Symptom: error messages that mention `landlock`, e.g. `error running landlock: Sandbox(LandlockRestrict)`.

Fix: check your linux kernel version. Codex requires locklock, which is available for kernel >= 5.15. 
See https://chatgpt.com/share/695d4d21-1598-800d-824a-26094ab109a0 for more information and how to upgrade your kernel version.
