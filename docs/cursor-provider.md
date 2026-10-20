<!-- Mirrored from the gnosis source repository by scripts/sync_public_docs.py — edit it there. -->

# Cursor as the inference provider

Audience: someone who wants gnosis's trajectory analysis to run on a Cursor plan, or who needs to
debug/extend that path. Code: `src/llm/cursor_auth.py` (binary, credentials, install),
`src/llm/cursor_chat.py` (the chat model), set-up in `src/commands/llm_setup.py`.

## One command

```bash
gnosis install --only llm --llm cursor --llm-key crsr_…
```

(or option 2, "Cursor API Key", in the `gnosis install` picker — docs/install-flow.md). The step
installs the Cursor Agent CLI when it is missing (`curl https://cursor.com/install -fsS | bash`;
`gnosis install --only cursor-cli` does just that), validates the key against the CLI, stores it,
persists `llm_provider = cursor` + `llm_auth_method = cursor`, warns when a configured model is not
offered to the account, and runs one healthcheck round trip. A CLI already signed in with
`agent login` needs no key. Undo with `gnosis logout --cursor-key`.

## How a call runs

Cursor has no public chat-completions API, so each request spawns the headless CLI:

```
agent -p --output-format json --mode ask --trust --model <model> --workspace <empty temp dir>
```

`--mode ask` means no file edits or tool side effects; the empty workspace keeps the agent from
reading a repository. Structured output is JSON requested in the prompt and parsed back into a
tool call, so `with_structured_output` works as with the other providers.

**Zero-priced**: Cursor bills per request on the plan and the CLI reports no token usage, so the
expense ledger shows $0 and no token counts for Cursor runs.

## Credentials (first hit wins)

1. `--key crsr_…` (only a Cursor-shaped key; an sk-ant key / JWT forwarded by the IDE is ignored)
2. `CURSOR_API_KEY`
3. the stored key — OS keychain (optional `keyring`) or `$GNOSIS_HOME/cursor-session.json` (0600)
4. the CLI's own `agent login`

## Models

| Tier | Default | Override |
|---|---|---|
| worker (Haiku-class calls) | `gpt-5-mini` | `CURSOR_MODEL`, `gnosis config set-cursor-model M` |
| main (Sonnet/Opus-class calls) | `claude-4.6-sonnet-medium` (Claude Sonnet 4.6) | `CURSOR_MAIN_MODEL`, `gnosis config set-cursor-model --tier main M` |

The defaults follow `agent models` naming but have **not been verified against a real account** —
check them with `agent models` (the install step warns when they are not listed).

## Environment

| Variable | Meaning |
|---|---|
| `CURSOR_AGENT_BIN` | Path to the `agent` binary (else PATH / `~/.local/bin`; older installs: `cursor-agent`). |
| `CURSOR_MODEL` / `CURSOR_MAIN_MODEL` | Per-tier model ids. |
| `GNOSIS_CURSOR_TIMEOUT_S` | Per-request timeout (default 600). |
| `GNOSIS_CURSOR_WORKSPACE` | Use this directory as `--workspace` instead of an empty temp dir. |
| `GNOSIS_CURSOR_PROMPT_VIA` | `argv`, `stdin` or `auto` (default) — how the prompt reaches the CLI. |
