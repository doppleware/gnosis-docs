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
| worker (Haiku-class calls) | `claude-haiku-5-5-low` (Haiku 5.5, no thinking; Cursor offers no Haiku 4.5) | `CURSOR_MODEL`, `gnosis config set-cursor-model M` |
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

## When Cursor says "sign in" but the CLI is signed in

A Cursor user (2026-10-20) saw analysis pause with `agent login` prompts and needed Cursor
restarts although the CLI was signed in. Three code causes were fixed:

- **Auth errors are read from the CLI's error text only.** `cursor_chat._error_text` searches an
  `is_error` result, stderr, or a stdout that is not a result document. A model answer that
  mentions "authentication" or a line number like 401 no longer reads as a credential rejection.
- **A sign-out verdict is cached 30 seconds, a sign-in 5 minutes.** An `agent status` that gives
  no answer (timeout, crash) is not a sign-out: a sign-in seen in the last hour still stands, and
  without one the next call asks again (`cursor_auth.status_verdict`, `cli_logged_in`).
- **A rejection the CLI contradicts is retried once.** When the CLI's own login is rejected and a
  fresh `agent status` still reports it signed in, the request runs once more after 3 seconds.

A rejection that persists raises `CursorAuthError` carrying a diagnostics record
(`llm/cursor_diagnostics.py`): the `agent` binary and version, the status verdict and its
latency, whether the CLI holds an access and a refresh token, the credential source, the
login cache, and the number of running `agent` processes. It is written to
`$GNOSIS_HOME/diagnostics/cursor-auth-*.json`, and its path rides the watch daemon's
`auth_required` event (`provider`, `stage`, `reason`, `report_path`) and the status snapshot's
`auth_gate_detail`.

## `gnosis install --llm-diagnostics [--repair] [--with-healthcheck]`

One JSON document for every provider (`commands/auth_diagnostics.py`): the LLM credential, the
call-graph credential and daemon, and every watch daemon's auth gate, with `problems[]` that
each carry a typed `remedy` a host can run (`gnosis` argv, `cursor-api-key` with a `{key}`
placeholder, or `pick-provider`). `--repair` pushes a missing or stale call-graph credential
and starts a stopped call-graph daemon, then re-checks. It never opens a browser or installs
anything. The air-vscode-plugin runs it on every `auth_required`.

**Call-graph and Cursor:** a Cursor CLI sign-in has no secret to hand over. A call-graph that
knows `auth set cursor --cli-login` (repo-arch-design, after 0.6.69) is told to use the
Cursor CLI's own sign-in instead, so the summaries need no API key; `--repair` does that.
An older call-graph gets `call-graph-credential-unshareable` with "Update call-graph".
A newer call-graph also records, per provider, the last request it saw refused, and
`auth status --format json` reports it as `health` (`last_error`, `last_error_at`,
`failing`, `current`). The diagnostics turn a `failing` record into
`call-graph-credential-refused` with the provider's fix (sign in to Cursor, a Cursor API
key, or Repair when gnosis holds a different credential).
