<!-- Mirrored from the gnosis source repository by scripts/sync_public_docs.py — edit it there. -->

# GitHub Copilot as the inference provider

Audience: someone who wants gnosis's trajectory analysis to run on a GitHub Copilot
subscription instead of a JetBrains AI login, or who needs to debug/extend that path.

## One command

```bash
gnosis install --only llm --llm copilot          # reuse the IDE sign-in, else device code at github.com/login/device
# or, with a token already issued to the Copilot app:
gnosis install --only llm --llm copilot --llm-key "$GITHUB_COPILOT_TOKEN"
```

(A plain `gnosis install` in a terminal asks the same question as option 4, "GitHub Copilot key".)

**`gh auth token` is not an exchange credential — but the Copilot API may take it directly.**
The GitHub CLI's token is issued to the `gh` OAuth app, and GitHub's Copilot token exchange only
honours tokens issued to the Copilot app itself, so the exchange rejects a `gh` token even on an
account that has Copilot (see "Diagnosing a rejected token" below). The Copilot API itself,
however, has been measured accepting that same token as its bearer (GitHub's own Copilot CLI
works this way): a Copilot Business seat (exchange 403, `/models` + chat 200, 2026-10-15 sign-in
report) and an individual account (2026-10-18). gnosis therefore falls back to the **direct
bearer** whenever the exchange refuses a token — see "Direct-bearer fallback" below — and the
setup step adopts a working `gh` login with no browser.

If Copilot is already signed in inside an IDE on this machine (VS Code, JetBrains, Neovim,
Copilot CLI), the step reuses that sign-in from `~/.config/github-copilot/apps.json`
or `hosts.json` after checking it can mint Copilot access — no browser, nothing copied; the token
stays owned by the IDE file and is re-read every run. With no IDE sign-in, a GitHub CLI login
(`gh auth token`) that Copilot accepts — through the exchange or as a direct bearer — is adopted
next, also with no browser (stored as the session, origin `gh-cli`; one attempt, never retried by
the fallback below). This is what makes the plugin's no-terminal run of the step work on a machine
that only has `gh`. Pass `--device` to skip both adoptions and sign gnosis in separately
(`--no-browser` prints the device URL instead of opening it). Even without running the step, that IDE sign-in is picked up automatically once the provider is
`copilot` (`gnosis config set-provider copilot` or `GNOSIS_LLM_PROVIDER=copilot`).

**When no sign-in window can open** (the device-code request fails, or no browser window opens),
the step falls back in order: the GitHub CLI's token (`gh auth token` — only under `--device`,
since otherwise it was already tried before the device flow; validated by a real Copilot call and
stored with origin `gh-cli`, the message says why when refused), then a hidden prompt for a GitHub
token with Copilot access (3 attempts).
Without a terminal there is no prompt; the error names `--llm-key`. `--no-browser` is
unaffected: it still prints the device URL and waits.

Otherwise it does three things:

1. **Stores the GitHub token** in the OS keychain (optional `keyring` package) or a 0600 file
   `$GNOSIS_HOME/github-copilot-session.json`, after verifying that the account can mint a
   Copilot token (i.e. actually has Copilot).
2. **Persists `llm_provider = copilot`** in `$GNOSIS_HOME/settings.json`. From then on every
   gnosis command runs on Copilot — including the many that never see `--provider`
   (`labs review`, `project fix`, the watch daemon's classify/TOC/analyze stages, chat bundles).
3. **Prints the model ids** the account can use and warns if the configured defaults are not
   among them.
4. **Runs the healthcheck** — one real Copilot round trip (`✓ llm: copilot healthcheck ok (model …)`);
   `--no-healthcheck` skips it, a failure keeps the token but exits non-zero.

Undo with `gnosis logout --github` (clears the token and resets the default provider), or
switch without logging out via `gnosis config set-provider anthropic`.

## Where Copilot sits among the LLM choices

`gnosis install`'s `llm` step (docs/install-flow.md) offers, in this order: JetBrains AI Credits,
Cursor API Key, Anthropic API Key, GitHub Copilot key. Copilot is `--llm copilot`. Whichever choice
runs the LLM, **code search (jbcontext) still needs the JetBrains sign-in**, so choosing Copilot
with no JetBrains session ends by offering it (in a terminal) or noting
`gnosis install --only sign-in` (without one).

## How the provider is chosen

```
--provider on the command          (pins the whole run — every LLMConfig preset follows it)
  > GNOSIS_LLM_PROVIDER
    > llm_provider in $GNOSIS_HOME/settings.json   (what `gnosis install --only llm --llm copilot` writes)
      > anthropic
```

`llm/provider_mode.py` owns this. Every `--provider` option in the CLI is declared with
`default=default_provider` (a callable) so the help text and the parsed default both follow
env/settings; `commands.cli.base.prepare` then calls `set_active_provider` for the process.

The Anthropic presets in `llm/config.py` are provider-aware: with `copilot` active,
`LLMConfig.claude_haiku_4_5_20251001()` returns the Copilot **worker** model and
`LLMConfig.for_anthropic_model(<sonnet/opus/fable id>)` the Copilot **main** model. That single
indirection is why no call site had to change.

## Models

| Tier | Used for | Default | Override |
|---|---|---|---|
| worker | the high-volume Haiku-class calls (classify, TOC, analyze, unit fan-out) | `gpt-4.1` | `GITHUB_COPILOT_MODEL`, or `gnosis config set-copilot-model MODEL` |
| main | Sonnet/Opus-class calls (review orient/adjudicate, project fix, diagrams) | `claude-sonnet-5` | `GITHUB_COPILOT_MAIN_MODEL`, or `gnosis config set-copilot-model --tier main MODEL` |

`gpt-4.1` is an "included" Copilot model (no premium requests), which is why it is the worker
default. Copilot bills per request (premium requests / AI credits), not per token, so Copilot
configs are zero-priced and the expense ledger shows `$0` for them — the accounting is on
GitHub's usage page. Model ids come from GitHub's model picker (`gnosis install --only llm --llm copilot` lists
them); an id Copilot does not offer fails at the first call with the API's own message.

## Credentials

`llm/copilot_auth.py` resolves the **GitHub token** in strict precedence:

1. `--key` on the command (request-scoped, never persisted)
2. `GITHUB_COPILOT_TOKEN`
3. the stored session (`gnosis install --only llm --llm copilot [--llm-key …]`)
4. a Copilot IDE plugin's sign-in (`apps.json` / `hosts.json` under `$XDG_CONFIG_HOME/github-copilot`,
   `~/.config/github-copilot`, or `%LOCALAPPDATA%\github-copilot`; `GITHUB_COPILOT_CONFIG_DIR` pins
   one). Ahead of `gh` because these tokens were issued to the Copilot app and can always mint
   Copilot access; a `gh` token may not.
5. the GitHub CLI's login (`gh auth token`) — GitHub's Copilot exchange rejects it on most
   accounts (see "Diagnosing a rejected token" below), but the direct-bearer fallback often
   makes it work anyway. Spawned per resolve, so the setup step stores it as the session instead
6. `GH_TOKEN` / `GITHUB_TOKEN` — what the Copilot CLI itself falls back to; last because CI
   tokens frequently carry no Copilot entitlement, and like `gh auth token` above these only
   work when that specific token was issued to the Copilot app

It then exchanges that for a short-lived **Copilot token** (`GET
https://api.github.com/copilot_internal/v2/token`, `Authorization: token <github token>`), which
carries the API host it is valid for (`endpoints.api`, e.g. `api.individual.githubcopilot.com`).
The Copilot token lives ~30 minutes and is cached in memory only, re-minted 2 minutes ahead of
expiry and once reactively when a call still 401s (`llm_invoke` replays the call once, same as
the JetBrains session path). `ChatCopilot` fetches it per request, so a client cached by
`create_llm` never carries a stale token.

### Direct-bearer fallback

When the exchange answers 401/403, `exchange_copilot_token` does not give up yet: it sends
`GET {GITHUB_COPILOT_API_BASE or https://api.githubcopilot.com}/models` with the **GitHub token
itself** as `Authorization: Bearer …` (plus the editor headers). A 200 whose body is a model list
(`{"data": [...]}` — a proxy's HTML 200 does not count) means the API accepts that token directly,
and `direct_bearer_token` returns it as the session token (`CopilotToken.mode == "direct"`, cached
like a minted one, re-probed hourly so a revocation or a newly working exchange is noticed). Only
when both refuse is the rejection diagnosed and raised. `/models` is free, so the probe never spends
a premium request; the log line `Copilot token exchange refused the GitHub token … using it that way`
and `mode direct` in `GitHub Copilot token minted (…)` say which path a run took. Because every
caller — runtime resolution, the IDE / `gh` adoption, `--llm-key` validation, the healthcheck — goes
through `exchange_copilot_token`, none of them needed to change.

Every request carries the editor identity headers the endpoint expects (`Editor-Version`,
`Editor-Plugin-Version`, `Copilot-Integration-Id: vscode-chat`). This is the same exchange the
third-party Copilot clients (LiteLLM's `github_copilot/` provider, OpenCode, aider, …) perform —
GitHub publishes no official chat-completions API for Copilot; the official programmatic
surface is the agent-oriented Copilot SDK, which is not a model endpoint. Two consequences
worth knowing:

- **Terms.** Using a Copilot subscription outside GitHub's own clients is tolerated but not
  documented; GitHub's abuse detection has flagged very high-volume automated use. Keep the
  worker tier on an included model and prefer the daemon's paced pipeline over bulk re-runs.
- **Enterprise.** Everything is overridable for GHE / proxy deployments:
  `GITHUB_COPILOT_TOKEN_URL`, `GITHUB_COPILOT_API_BASE`, `GITHUB_COPILOT_DEVICE_CODE_URL`,
  `GITHUB_COPILOT_ACCESS_TOKEN_URL`, `GITHUB_COPILOT_CLIENT_ID` (the OAuth app for the device
  flow), `GITHUB_COPILOT_EDITOR_VERSION` / `GITHUB_COPILOT_PLUGIN_VERSION`.

### Diagnosing a rejected token

A 401/403 from the token exchange used to always say "the token is invalid, expired, or the
account has no Copilot subscription" — true as a disjunction, but misleading for the single
most common case: a **valid, non-expired token issued to the wrong OAuth app**. GitHub's
Copilot token exchange only honours tokens issued to the Copilot app's own sign-in; a `gh auth
token` (GitHub CLI, OAuth client id `178c6fc778ccc68e1d6a`), a fine-grained `github_pat_…`
token (even with the "Copilot Requests" permission), or any other app's token are all rejected
with the same bare 403 regardless of whether the account has Copilot.

`exchange_copilot_token` (`src/llm/copilot_auth.py`) now diagnoses a 401/403 before raising:
one `GET /user` with the same token (a 401 there means the token really is invalid/expired;
otherwise its `x-oauth-client-id` response header names the OAuth app it belongs to), then one
`GET /copilot_internal/user` to check whether the account has a Copilot subscription at all.
`describe_exchange_rejection` (pure, network-free, unit-tested) turns that into one of:

- *wrong app, account has Copilot* — names the GitHub CLI specifically when the client id
  matches, else "another app's token"; states the plan; points at the device sign-in.
- *fine-grained PAT, account has Copilot* — same remedy, with the PAT-specific note that even
  the Copilot Requests permission doesn't make a PAT acceptable here.
- *account has no Copilot subscription* — names the account's login.
- anything a probe doesn't resolve (probe failed, unexpected shape, `/user` itself rejected
  for an unrelated reason) — the original generic message; the diagnosis never raises and never
  replaces a real error with a wrong one.

## Reporting a failure

When a Copilot sign-in fails, the error carries what we need to diagnose it
(`src/llm/copilot_diagnostics.py`). It stays ONE line, because the install ✓/✗ protocol and
the healthcheck verdict read only the first line:

```
✗ llm: … GitHub CLI token … Your account HAS Copilot (business). … [exchange 403 req ABCD:123456 ·
  direct /models 401 req EF01:7890 · /user 200 req … · token gho_… len 40 fp 0123abcd from gh-cli ·
  app GitHub CLI · plan business · proxy http://proxy.example.com:8080] — full report: ~/.gnosis/diagnostics/copilot-auth-….json
```

- **Steps**, in order: the token exchange, the direct-bearer `/models` probe, `GET /user`,
  `GET /copilot_internal/user`, each with its HTTP status and GitHub's `x-github-request-id`
  (what GitHub support asks for), or the transport error (TLS interception, proxy refusal).
- **The token's shape, never the token**: prefix, length, sha256 fingerprint, and where it came
  from (session / ide / gh-cli / login-token / env). The OAuth app (`x-oauth-client-id`, named
  when known), scopes, Copilot plan and SKU.
- **The full report** is a 0600 JSON file under `$GNOSIS_HOME/diagnostics/` (the last 10 kept),
  adding redacted body snippets, latencies, OS / Python / gnosis version, every proxy variable
  (userinfo stripped) and the `GITHUB_COPILOT_*` / CA-bundle overrides in effect. Bodies are cut
  to 200 characters and masked: the token, anything token-shaped and `Bearer …` values
  (`/models` really does echo the token on a 401).
- **`gnosis install --llm-healthcheck`** adds `report_path` + `details` (the record) to its JSON
  verdict, so a host can show it or attach the file. An unreachable endpoint raises
  `CopilotUnreachableError` (still a `RuntimeError`) with the same record.
- **Chat-time failures** (a model the plan does not offer, a revoked bearer) name the model, the
  API host, the token mode (exchange/direct), the credential source, the request id and the proxy.

embark-call-graph puts the same one-line detail block (steps + request ids, token shape, proxy)
into its own Copilot errors.

## Why not "GitHub token as `OPENAI_API_KEY`"

A common recipe points `ChatOpenAI` at Copilot with the GitHub token as the API key. An earlier
version of this page said that never works because the chat API only accepts the exchanged
~30-minute Copilot token. That is wrong for some tokens: `api.githubcopilot.com` has been measured
accepting a `gh` token directly (see "Direct-bearer fallback"). It is not the default here for
two reasons: the exchanged token names the per-plan API host (`endpoints.api`), which a static
key cannot, and not every token works directly — the exchange stays the first attempt, the direct
bearer the fallback, both behind the same refresh. Its other two points do apply and are
handled: 429s are retried with backoff in `ChatCopilot`, and structured output uses a forced
tool call rather than OpenAI's strict JSON-schema mode, which the Copilot gateway does not
reliably support. The recipe's `gpt-4o` is superseded in Copilot by `gpt-4.1`, the default here.

## Module map

| Module | Role |
|---|---|
| `src/llm/provider_mode.py` | Active-provider resolution (`--provider` > env > settings > anthropic). Stdlib-only, on the CLI startup path. |
| `src/llm/copilot_diagnostics.py` | The shareable record of a failed sign-in attempt (steps, request ids, token shape, identity, environment) — one-line summary + redacted JSON report. |
| `src/llm/copilot_auth.py` | GitHub token resolution + persisted session, Copilot token exchange/cache/refresh, device-code login, model listing. httpx loads lazily. |
| `src/llm/copilot_chat.py` | `ChatCopilot(BaseChatModel)`: OpenAI chat-completions over httpx, `bind_tools` for structured output, usage/model metadata, tiktoken counting, 429/5xx backoff. |
| `src/llm/config.py` | `LLMConfig.copilot*` presets and the tier routing of the Anthropic presets. |
| `src/llm/client.py` | `_build_llm` copilot branch; `has_llm_auth(provider)`. |
| `src/llm/invoke.py` | `_try_session_refresh(config)`: re-mint-and-replay for copilot. |
| `src/commands/llm_setup.py` (`github_setup`), `src/commands/cli/install.py`, `src/commands/cli/logout.py` | `gnosis install --only llm --llm copilot`, `gnosis logout --github`. |
| `src/commands/cli/config.py` | `gnosis config set-provider / set-copilot-model / show`. |
| `src/settings.py` | `llm_provider`, `copilot_model`, `copilot_main_model`. |
| `tests/test_copilot_provider.py` | The whole path with stubbed network. |

## Why not `langchain-openai`

Every 1.x release of `langchain-openai` requires `langchain-core >= 1.5`, and this project pins
`langchain-core == 1.4.8` together with `langchain` / `langchain-anthropic` (see the pin comment
in `pyproject.toml`). Bumping the stack for one provider would have changed structured-output
behaviour for every existing Anthropic call. The Copilot wire format is plain OpenAI chat
completions, and the two Copilot-specific needs — a bearer re-minted every ~30 minutes and the
editor headers — are things a stock OpenAI client would need wrapping for anyway, so
`ChatCopilot` speaks the format directly over httpx (already a dependency). If the pins move to
`langchain-core >= 1.5`, `ChatCopilot` could become a thin `ChatOpenAI` subclass; the auth
module would stay as is.

## IDE plugin

The VS Code plugin drives `gnosis install --only sign-in` (JetBrains) and
`gnosis install --only llm --llm <choice> [--llm-key KEY]` from user gestures, and reads the
resulting state from `gnosis install --status` (`knowledgebase.llm_provider` /
`llm_auth_method` / `jetbrains_session`). The persisted `llm_provider` setting is honoured by every
command it spawns.
