# Troubleshooting

## Codex Node version error
```bash
$ sudo npm install -g @openai/codex
npm WARN notsup Unsupported engine for @openai/codex@0.77.0: wanted: {"node":">=16"} (current: {"node":"10.19.0","npm":"6.14.4"})
```
```bash
$ codex
/usr/local/lib/node_modules/@openai/codex/bin/codex.js:4
import { spawn } from "node:child_process";
```
Follow this to update node version: https://nodejs.org/en/download#debian-and-ubuntu-based-linux-distributions-enterprise-linux-fedora-and-snap-packages
