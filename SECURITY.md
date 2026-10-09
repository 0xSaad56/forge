# Security Policy

## Supported versions

This project is in active early development. Security fixes are applied on a best-effort basis to the default branch.

## Responsible use

Forge is intended for authorized security research, defensive analysis, education, and controlled laboratory environments. Do not use it to access systems or data without permission.

The maintainers do not provide assistance for unauthorized intrusion, fraud, or other illegal activity.

## Reporting a vulnerability

If you believe you have found a security issue **in Forge itself** (for example path traversal in the local API, unsafe deserialization, or unintended network exfiltration):

1. **Do not** open a public GitHub issue with exploit details.
2. Contact the repository owner through GitHub Security Advisories (preferred) or a private channel listed on the owner profile.
3. Include: affected version/commit, reproduction steps, impact assessment, and any suggested fix.

You should receive an acknowledgement when the report is seen. Coordination of disclosure is handled case by case.

## Out of scope

- Issues that exist only in third-party models (GGUF weights, embedding models)
- Content quality of Exploit-DB / NVD data the user imports
- Misconfiguration of `llama-server` or OS-level exposure of ports beyond loopback
- Prompt-injection outcomes when the user indexes untrusted documents (mitigate by treating knowledge as data, not instructions—the app prompts are written with that in mind, but no LLM stack is immune)

## Local deployment hardening (recommended)

- Keep UI and `llama-server` on `127.0.0.1`
- Do not set `FORGE_ALLOW_REMOTE_LLM=1` unless you accept leaving the machine
- Use filesystem permissions (`0700` on data dirs) on shared hosts
- Exclude `knowledge/`, `data/`, and `chats/` from sync/backup to untrusted clouds if they contain sensitive research
