<!-- Mirrored from the gnosis source repository by scripts/sync_public_docs.py — edit it there. -->

# `gnosis install` — the setup flow

> The end-to-end first-run workflow as the air-vscode-plugin drives it — setup gate, wizard
> steps, the one-login hand-off to jbcontext, the chosen-credential healthcheck, call graph on
> by default, and the tear-down commands — is recorded in the plugin repo at
> `docs/first-run-setup.md` (2026-10-01). This document is the CLI-level reference it builds on.

`gnosis install` is the one setup command: it signs you in, installs the external CLIs and
picks the LLM that runs trajectory analysis. There is **no `gnosis login` command** any more
(removed 2026-09-30); its behaviour lives in the `sign-in` and `llm` steps below. Code:
`src/commands/install.py` (orchestration + components), `src/commands/llm_setup.py` (the two
account steps + `gnosis logout`), `src/commands/cli/install.py` (flags).

```
gnosis install
 ├─ 1. sign-in      Log in to the JetBrains account, select the AI license / organization
 ├─ 2. jbcontext    (its login IS the gnosis JetBrains session — token_store.jetbrains_cli_env)
 │     chatter
 │     call-graph   (also ensures its daemon is running)
 │     status-ui    (only when named; macOS/Windows; not on PyPI yet)
 │     cursor-cli   (only when named, or when step 3 picks Cursor)
 └─ 3. llm          "Gnosis requires some LLM inference for trajectory analysis, what would you like to use?"
                      1. JetBrains AI Credits → the step-1 session, then healthcheck
                      2. Cursor API Key       → install the Cursor CLI, ask for the key, healthcheck
                      3. Anthropic API Key    → ask for the key, healthcheck
                      4. GitHub Copilot key   → key, or reuse the IDE's Copilot sign-in / device flow, healthcheck
```

## Selection

`--only NAME` (repeatable) runs just the named steps/components, always in the canonical order
`sign-in → jbcontext → chatter → call-graph → status-ui → cursor-cli → llm`, whatever order the
flags came in. Without `--only` the default set is everything except `status-ui` and `cursor-cli`.

## Flags

| Flag | Step | Meaning |
|---|---|---|
| `--only sign-in\|jbcontext\|chatter\|call-graph\|status-ui\|cursor-cli\|llm` | — | Run only these (repeatable). |
| `--update`, `--force` | components (+ cursor-cli via the llm step) | Upgrade installed ones / reinstall from scratch. |
| `--status` | — | Read-only JSON, installs nothing; rejects every flag below. |
| `--remove` | — | Tear-down (`commands/install_remove.py`): stops every watcher, clears every credential + the LLM choice (`logout --all` + `jbcontext logout`), uninstalls the components through their own channels in the order `llm → sign-in → cursor-cli (only when named) → status-ui → call-graph → chatter → jbcontext`. `--only` narrows it. A pinned call-graph binary, gnosis itself, settings pins and the data stay. Rejects every other flag. |
| `--remove-data` | — | Deletes every store and cache: the conversation DB (+ WAL/SHM/backups), `$GNOSIS_HOME/{llm-cache,projects,watch,experiments,shared_storage_cache,review-rules}`, `~/.cache/gnosis`, `~/.embark-call-graph`, `~/.jbcontext/cache`. Stops the watchers and the call-graph daemon first. Combinable with `--remove`; takes no `--only`. |
| `--yes` / `-y` | remove | Skip the terminal confirmation (a non-TTY run — the plugin — never prompts). |
| `--jetbrains-token JWT` | sign-in | Store this JWT instead of signing in interactively (validated with one refresh round trip). |
| `--jetbrains-license-id ID` | sign-in | Use this AI license — no picker. Naming an id makes the step explicit (attempted even in the default set without a TTY). |
| `--jetbrains-workspace-id ID [--jetbrains-org-id ID]` | sign-in | Use this AI Seats workspace — no picker (the org id disambiguates and is checked when given). |
| `--jetbrains-access-list` | sign-in | Print the AI access options as JSON and exit 0 — nothing minted or stored. |
| `--llm-healthcheck` | llm | ONE real round trip with the RECORDED choice, authenticated with that choice's own credential (stored Anthropic key / JetBrains session pinned through the request-key tier — never Claude Code's apiKeyHelper or an env token); prints `{passed, choice, provider, model, credential, latency_ms, error}`, exit 1 when not passed or no choice recorded. The llm step's own healthcheck pins the same way and its ✓ note names the credential. |
| `--jetbrains-session-token` | sign-in | Print the current session JWT (renewed when stale) and exit 0; exit 1 with no usable session. For a host that spawns jbcontext itself (the plugin's semantic search) and injects it as `JETBRAINS_AI_PLATFORM_TOKEN` — one sign-in serves gnosis and jbcontext. Takes no other option. |
| `--llm jetbrains\|cursor\|anthropic\|copilot` | llm | The choice; without it a terminal gets the numbered picker (current choice marked). |
| `--llm-key KEY` | llm | The Cursor / Anthropic / GitHub key. Ignored (with a note) for `jetbrains`. Without it: the key gnosis already stored is reused, else a terminal prompts, else error. |
| `--no-healthcheck` | llm | Skip the round trip. |
| `--device` | llm copilot | Always run GitHub's device sign-in, even when an IDE sign-in could be reused. |
| `--no-browser` | llm copilot, `--cursor-login` | Print the sign-in URL instead of opening the browser. |
| `--cursor-login` | llm cursor | Sign in with the Cursor ACCOUNT (`agent login`) instead of pasting an API key. Implies `--llm cursor`; a usage error with `--llm-key` or another `--llm`. Works without a terminal. |

## The sign-in step

1. `--jetbrains-token` → `token_store.login_with_token`.
2. A stored session that resolves (resolution renews a stale-but-refreshable one) → `✓ sign-in:
   already signed in — … (token expires …)`; no browser.
3. Else the JetBrains Daemon (no browser; the only way to mint AI Seats workspace *AI* tokens), else the
   browser OAuth + PKCE flow, then the license / workspace pick — auto-picked when unambiguous
   (single enabled workspace > single enabled option), a numbered prompt in a terminal, the
   **browser picker** without one (below). Mechanics: stateful-login.md.
   An option the user PICKED (terminal prompt / browser picker) is honoured as-is — a refusal never
   trades it for another workspace; only an auto-picked option walks the other enabled options
   (the AI Platform's first-success-wins doctrine for licenses). The session records the pick's
   display name (`selection_display` → `--status` `jetbrains_session.selection` / `selection_kind`).
4. When NO option yields an AI Platform token (a workspace without the daemon — `embark-cli` may not
   `switch_audience` into the AI audiences; a cardless personal license — HTTP 492), gnosis does what
   jbcontext does: `switch_audience` into **`embark-server`** for the workspace
   (`jcp_oauth.mint_workspace_code_search_token`) and stores a **code-search session**
   (`JetBrainsSession.token_kind = "jcp-embark-server"`). It serves jbcontext (handed over as
   `JCP_TOKEN` — `jetbrains_cli_env`, `install --jetbrains-session-token` prints `VAR=token`) but is
   NOT an LLM credential: `resolve_llm_session_token` skips it, `--status` reports
   `jetbrains_session.kind` + `llm_capable:false`, and the llm step refuses `--llm jetbrains` with the
   daemon remedy. Only a license-only account with every option refused still fails (one-line reasons).

## Choosing the AI access

After the daemon / OAuth bootstrap and before any token is minted, gnosis picks ONE option from
`ai-access-options` (licenses and AI Seats workspaces):

1. **By id** — `--jetbrains-license-id ID`, or `--jetbrains-workspace-id ID [--jetbrains-org-id ID]`
   (jbcontext's `account --license-id | --workspace-id --org-id`). Wins over auto-pick; an id that
   matches nothing is `✗ sign-in: No JetBrains AI access option matches … Available:` followed by
   every enabled option and the flags that select it; a disabled one says "AI access is not
   enabled". The chosen option is minted as-is (no walk to other options on refusal). With a valid
   stored session for the SAME selection the step is `already signed in`; a DIFFERENT selection
   switches (no `gnosis logout` needed), reusing the stored OAuth refresh token when there is one
   (no browser).
2. **Auto-pick** — single enabled workspace > single enabled option.
3. **Terminal** — the numbered "Select your JetBrains AI access" prompt.
4. **No terminal** (the IDE plugin's `install --only sign-in` spawn) — the **browser picker**
   (`jcp_oauth.browser_select_option`): a one-shot HTTP server on a free `127.0.0.1` port serves
   "Choose your JetBrains AI access — Select a license or a workspace available to your account",
   one button per option (name, `license`/`workspace` badge, org name for workspaces; disabled
   options greyed "AI access not enabled") plus "Cancel sign-in". The page URL and the form carry a
   one-time CSRF token — a request without it is a 403 and the server keeps waiting. The POST
   answers "You can close this tab" and the sign-in continues (mint → store). The page opens with
   `webbrowser.open`; the URL is always printed as a fallback. 5 minutes without a choice → `✗
   sign-in: Timed out waiting for a JetBrains AI access choice …` naming the id flags.

The selection ids are stored on the session (`license_id` / `org_id` + `workspace_id`), so
renewal re-mints the same option and a re-run never asks again.

**`--jetbrains-access-list`** signs in (stored session's OAuth refresh token → daemon → browser)
and prints exactly one JSON document on stdout (progress on stderr), minting and storing nothing:

```json
{"options": [
  {"kind": "license", "id": "L1", "display": "All Products — Jane", "enabled": true, "current": false},
  {"kind": "workspace", "id": "ws-1", "org_id": "org-1", "org_name": "Acme", "display": "Team — Acme",
   "enabled": true, "current": true}
]}
```

`current` marks the stored session's selection. A host can draw its own picker from it and come
back with `--only sign-in --jetbrains-license-id …`. It cannot be combined with other `--only`
steps, `--jetbrains-token`, an option id, `--llm`/`--llm-key` or `--status`. Without a daemon or a
stored OAuth session, listing and then selecting costs two browser sign-ins (the listing run
stores nothing).

The step never changes the LLM choice.

## The llm step

| Choice | Credential | `llm_auth_method` | `llm_provider` | Healthcheck provider |
|---|---|---|---|---|
| `jetbrains` | the sign-in session (offered in a terminal when missing; else error pointing at `--only sign-in`) | `gateway` | cleared | anthropic |
| `cursor` | Cursor CLI installed first when missing (`cursor_auth.install_cursor_cli`); an already `agent login`ed CLI needs no key; else key → `validate_key` → `save_key` | `cursor` | `cursor` | cursor |
| `anthropic` | key → `anthropic_key_store.validate_key` (free `GET /v1/models`) → `save_key` | `anthropic-key` | cleared | anthropic |
| `copilot` | `--llm-key` → `copilot_auth.login_with_github_token`; else stored session, else the IDE's Copilot sign-in, else device flow | `copilot` | `copilot` | copilot |

**`--cursor-login`** (the IDE plugin spawns `gnosis install --only llm --llm cursor --cursor-login` from
a user gesture, no TTY): install the Cursor CLI when missing → if `agent status` already reports an
authenticated account, say so and skip; else `cursor_auth.run_cli_login` runs `agent login` with stdin
detached (it opens the browser itself; `--no-browser` sets `NO_OPEN_BROWSER=1` so it prints the URL,
which streams as a `[llm]` detail line), 5-minute timeout, then re-checks `agent status` (exit 0 but no
account → `✗ llm: Cursor sign-in failed: signed in, but agent status does not report an authenticated
account`). A failed sign-in carries the CLI's last lines and records nothing. On success a stored Cursor
API key is **deleted** (in `resolve_cursor_auth` a stored key outranks the CLI login, so it would
silently win over the choice just made); an ambient `CURSOR_API_KEY` still outranks it and is noted.
Then the choice is recorded and the healthcheck runs. `gnosis logout` never touches the CLI's login
(it belongs to the user's Cursor install) — `logout --all` prints that `agent logout` clears it.

A rejected credential is not stored and the method is not recorded. After a non-JetBrains choice,
**when no JetBrains session exists**, the step notes that code search (jbcontext) still needs the
sign-in — offering it in a terminal.

**Healthcheck** = one real round trip **with the chosen credential**
(`llm_setup.llm_healthcheck(provider, choice)`): `set_active_provider(p)`, then — because the
`anthropic` provider's resolver prefers Claude Code's `apiKeyHelper` ("wire") and env tokens over
the stored key / session — the choice's own credential is pinned through the request-key tier
(`set_request_key`, which outranks wire + env; restored afterwards): the stored Anthropic key for
`anthropic`, the JetBrains session for `jetbrains` (a code-search session — see "Session kinds" — is
refused with the Toolbox remedy). `cursor` / `copilot` run on their own providers and need no pin.
Then `create_llm(get_llm_config(p)).invoke("Say ok", max_tokens=1)` →
`✓ llm: <provider> healthcheck ok (model <id>, credential: <stored Anthropic key | JetBrains session |
Cursor login/key | GitHub Copilot session>)`. On failure: `✗ llm: <provider> healthcheck failed:
<first line of the error> …`, exit non-zero — the stored credential is **kept** (fix the cause,
re-run `gnosis install --only llm`). Without the pin a healthcheck for "Anthropic API key" passed on
the wire credential and proved nothing about the key just stored (2026-10-01: a cancelled Copilot
sign-in read as working).

## Call-graph credential

The call-graph daemon summarizes code with an LLM too. After the llm step's healthcheck passes (or
after a `--no-healthcheck` configure), `commands/callgraph_auth.push_llm_credential` hands the same
credential to embark-call-graph, and the ✓ line gains a suffix, e.g. `✓ llm: anthropic healthcheck ok
(model …) — call-graph: grazie credential pushed`.

| Choice | call-graph provider | Secret |
|---|---|---|
| `jetbrains` | `grazie` | the live session JWT (`usable_jetbrains_token`); none → note |
| `anthropic` | `anthropic` | the stored key (`anthropic_key_store.load_key`) |
| `copilot` | `copilot` | the stored GitHub token (`copilot_auth.load_session().github_token`), else the IDE's Copilot sign-in token; none → note |
| `cursor` | `cursor` | the stored key (`cursor_auth.load_key`); a CLI-login user has none → note "Cursor CLI login cannot be shared with call-graph; set a Cursor API key for it with `embark-call-graph auth set cursor --stdin`" |

Mechanics: no `embark-call-graph` binary (`install._resolve_call_graph`) → nothing, no note.
`auth status --format json` first — when it reports the provider `configured` with the fingerprint
`sha256(secret)[:8]` the note is `call-graph: already has this <provider> credential` and nothing is
written. Else `auth set <provider> --stdin` with the secret on **stdin** (never argv or env), 15 s
timeout. An older call-graph that rejects the provider ("invalid choice"/"Invalid value"/no `auth`
verb) → `call-graph: this embark-call-graph does not accept <provider> credentials yet — upgrade it
…`. Every failure is a `call-graph: …` note on the ✓ line, never a ✗. A failed healthcheck pushes
nothing.

JetBrains caveat: call-graph receives the JWT **as it is now**. gnosis renews its own session but
does not re-push; refreshing the token on the call-graph side is call-graph's job.

## Output protocol

Every step/component prints a `── name ──` header, indented `  [name] …` detail lines, then
exactly one of:

- `✓ name: <note>` — done;
- `✗ name: <message>` (stderr) — failed; the run continues, and ends with
  `Error: failed to install: a, b` and exit 1;
- `  [name] skipped: <reason>` — deliberately not run (not a failure).

## Non-interactive rules

"Interactive" = stdin AND stdout are TTYs.

- **Default set, no terminal**: `sign-in` is skipped when no usable session exists
  (`skipped: no JetBrains session and not running in a terminal — run gnosis install --only
  sign-in …`), `llm` is skipped when `--llm` is absent. A bare `gnosis install` in CI never opens
  a browser or waits on a prompt, and stays green.
- **Explicit `--only sign-in`** always attempts the sign-in (daemon, else browser) — the IDE
  plugin spawns exactly that from a user gesture with no TTY. An ambiguous license/workspace pick
  opens the browser picker there (it used to be an error).
- **Explicit `--only llm` without `--llm`** → `✗ llm: --llm is required when not running in a terminal.`
- A missing `--llm-key` without a terminal reuses the stored key, else errors
  (`--llm-key is required when not running in a terminal.`); copilot without a key reuses the IDE
  sign-in / runs the device flow (it prints the code; no prompt).

## `--status` additions (schema stays 1, additive)

- `components` may contain `cursor-cli`: `{installed, path, version, available}`
  (`available=false` when this build has no Cursor support). Steps are never components:
  `--status --only sign-in` reports `components: {}`.
- `knowledgebase` gains:
  - `llm_provider` — the effective provider (env `GNOSIS_LLM_PROVIDER` > settings > `anthropic`);
  - `llm_auth_method` — `gateway | cursor | anthropic-key | copilot | null`;
  - `jetbrains_session` — `{present, expires, kind, llm_capable, selection, selection_kind}`, read
    from the store only (no refresh, no network): `kind` = `ai-platform | jcp-embark-server | null`,
    `llm_capable` = `kind == "ai-platform"`, `selection` = the chosen access option's display name
    (`"Team — Acme"`, recorded since 2026-10-01 — older sessions report `null`),
    `selection_kind` = `workspace | license | null`.
  - `instrumentation` — one row per `--status --project DIR` (repeatable; a multi-root IDE workspace
    passes one per folder; default = the enclosing repo): `{project, requested, instrumented,
    complete, missing, surfaces, watcher}` from `commands.instrument.instrumentation_state` —
    read-only, follows instrument's linked-worktree redirect (`requested` = the folder asked about
    when it redirected to the main checkout). `surfaces` = every project surface `gnosis instrument`
    writes: `search_skill`, `knowledge_skill`, `claude_md`, `agents_md`, `permissions`,
    `sandbox_exclusions`, `gitignore` (`null` outside a git work tree — not applicable, never
    "missing") and `watcher` (live per-scope record). `instrumented` keeps the historic meaning
    (the search skill, as `instrument --check`); an unreadable folder is `{project, error}`.
- `components.call-graph.flows_wiring` — `{wired, skill, claude_md}`: the plugin's code-flows skill
  and its managed CLAUDE.md block, each found at `project` or `user` scope (Claude Code loads
  both). `flows_skill_installed` now means the skill at EITHER scope — it checked the project
  only, so the plugin's default user-scope wiring showed as "Flow tools: Not wired" (2026-10-02).

`llm_credentials` / `llm_credentials_source` keep their meaning (cursor reports source `cursor`).

## Session kinds

A stored JetBrains session (`token_store.JetBrainsSession.token_kind`) is one of two things:

| `token_kind` | What it is | Serves | Handed to jbcontext as | Renewal |
|---|---|---|---|---|
| `ai-platform` (default — every pre-existing session) | a Grazie JWT minted via the daemon (workspace) or `provide-access` (license) | LLM inference (JetBrains AI Credits) **and** code search | `JETBRAINS_AI_PLATFORM_TOKEN` | Grazie refresh endpoint, then re-mint |
| `jcp-embark-server` | the workspace token jbcontext itself signs in with when no daemon runs: `switch_audience` into `embark-server` over our OAuth session (`jcp_oauth.mint_workspace_code_search_token`) | code search only | `JCP_TOKEN` | re-mint only (never the Grazie endpoint) |

`run_interactive_login` falls back to the second kind when **no** option yields an AI-platform token:
the `embark-cli` OAuth client is refused the AI audiences for a workspace (`grant_type_not_allowed` —
only the daemon's `jetbrainsd` client may mint them) and a cardless personal license gets
HTTP 492. The ✓ note then reads `signed in with workspace '…' for code search … JetBrains AI inference
needs the JetBrains Daemon (Toolbox)`. A code-search session is **not** an LLM credential:
`token_store.resolve_llm_session_token()` returns `None` for it (the `anthropic` resolver's session
tier falls through), `--llm jetbrains` is refused with the Toolbox remedy, `--status` reports
`llm_capable: false`. Only a license-only account with every option refused still fails, in one line
naming each option and why (`no_option_minted_message`), with the paste-a-token fallback.

An option the user **picked** (terminal prompt / browser picker) is honoured as-is — a refusal never
trades it for another workspace; only an auto-picked option walks the other enabled options.

## Host queries

Read-only (or single-round-trip) verbs for a host that drives the setup — the air-vscode-plugin's
first-run wizard. Each prints exactly one document on stdout and takes no other option.

| Flag | Prints | Exit |
|---|---|---|
| `--status` | the install/knowledgebase state (above) | 0 always |
| `--jetbrains-access-list` (with `--only sign-in`) | `{options:[{kind,id,org_id?,display,enabled,current}]}` — signs in (stored refresh token → daemon → browser) without choosing, minting or storing | 0 |
| `--jetbrains-session-token` | `VAR=<session JWT>` — `VAR` is `JETBRAINS_AI_PLATFORM_TOKEN` or `JCP_TOKEN` per the session kind; renewed when stale. The host injects exactly that variable into the jbcontext processes **it** spawns, so one sign-in serves gnosis and semantic search (`token_store.jetbrains_cli_token_var`, mirroring `jetbrains_cli_env`) | 1 with no usable session |
| `--llm-healthcheck` | `{passed, choice, provider, model, credential, latency_ms, error}` — the recorded choice's healthcheck, pinned to its own credential exactly like the llm step's (`llm_setup.healthcheck_report`) | 1 when not passed or nothing is chosen (`error: "no LLM provider chosen — …"`; an ambient credential answering a probe is not a configured provider) |

## Tearing down: `--remove` / `--remove-data`

The reverse of the default set (`commands/install_remove.py`); both halves combine, both stop every
watch daemon first, both confirm in a terminal unless `--yes` (a non-TTY run — the plugin behind its
own modal — never prompts). Same `── name ──` / `✓ name:` / `✗ name:` protocol with two extra targets,
`watch` and `data`; a failing target is reported and the rest continues; exit non-zero names the
failures.

**`--remove [--only NAME]...`** — order `llm → sign-in → cursor-cli → status-ui → call-graph → chatter
→ jbcontext` (credentials first; the jbcontext binary last because `sign-in` runs `jbcontext logout`
through it):

| Target | Does |
|---|---|
| `llm` | deletes the Anthropic key, Cursor key, Copilot session; clears `llm_auth_method` / `llm_provider` (`gnosis logout --all`) |
| `sign-in` | `jbcontext logout` + deletes the JetBrains session |
| `cursor-cli` | **only when `--only cursor-cli`** (mirrors install's default set): the installer's `~/.local/bin/{agent,cursor-agent}` symlinks + `~/.local/share/cursor-agent`; a binary elsewhere is the user's own |
| `status-ui` | kills the tray process, `uv tool uninstall gnosis-status-ui` |
| `call-graph` | `embark-call-graph daemon stop`, `uv tool uninstall embark-call-graph` — a **pinned** binary (`EMBARK_CALL_GRAPH_BIN` / `gnosis config set-call-graph-bin`) is the user's own build and is left in place |
| `chatter` | `$GNOSIS_HOME/bin/chatter` + `chatter-meta.json` (a `CHATTER_PATH` binary is external and untouched) |
| `jbcontext` | `~/.jbcontext` (the hosted installer's whole home) + a dangling `~/.local/bin/jbcontext` shim; a `JBCONTEXT_BIN` outside it is untouched |

gnosis itself, `$GNOSIS_HOME/settings.json` pins (`call_graph_bin`, `shared_storage_repo`) and the data
stay — the plugin's next activation runs its first-time flow (provider picker, sign-in, installs).

**`--remove-data`** (no `--only`) — also stops the call-graph daemon, then deletes
(`install_remove.data_paths`, honouring `GNOSIS_DB_PATH` / `GNOSIS_HOME` / `XDG_CACHE_HOME` /
`EMBARK_CALL_GRAPH_PROFILE`): the conversation DB + its `-wal` / `-shm` / `.bak-*` siblings, a legacy
`$GNOSIS_HOME/gnosis.sqlite3*`, `$GNOSIS_HOME/{llm-cache,projects,watch,experiments,shared_storage_cache,
review-rules}`, `~/.cache/gnosis` (classifier vectors, embedding model, labs caches),
`~/.embark-call-graph` (call-graph snapshots + logs) and `~/.jbcontext/cache`. `$GNOSIS_HOME/{bin,
settings.json,session-*}` and every credential stay — those are `--remove`'s.

Neither touches the per-project `gnosis instrument` surfaces (skills, CLAUDE.md block, sandbox
exclusions) — `gnosis instrument --remove` per project does; the plugin re-instruments on activation.

## Pinned call-graph binary

`EMBARK_CALL_GRAPH_BIN` (env) or `gnosis config set-call-graph-bin PATH|default` (`settings.call_graph_bin`;
`settings.configured_call_graph_bin()` is the one resolver every spawn site reads: `commands/install.py`,
`commands/knowledge/external.py`, `capabilities.py`) names a call-graph build under test. While pinned,
`gnosis install` never installs, upgrades or reinstalls call-graph (any flag) — it only ensures the pinned
binary's daemon is running, and an unresolvable pin is an error rather than a silent fall-back to the
Grazie build. `--remove` leaves it in place. A running watch daemon keeps the binary it started with
(`gnosis watch stop` / `start`). The air-vscode-plugin's dev host sets the pin from its `.env`
(`EMBARK_CALL_GRAPH_SRC` builds the checkout editable; `EMBARK_CALL_GRAPH_BIN` uses a binary as-is).

## jbcontext opt-out

`gnosis config set-jbcontext off|on` (`settings.jbcontext_disabled`; env `GNOSIS_JBCONTEXT=off|on` outranks it
per run; `settings.jbcontext_opted_out()` / `capabilities.code_search_opted_out()` are the one check every site
reads, fresh on every call so a live watch daemon sees a toggle) turns jbcontext off for gnosis without
uninstalling it. Off means: `gnosis install` never installs or updates it (a green
`jbcontext: disabled by the user` line, so a batched `--update` is not a failure; `--status` carries
`components.jbcontext.disabled` and skips the index probe; `status health` counts it ok); the watch daemon's
worktree index stage and `instrument`'s worktree code-search step stand down; `knowledge search-code` /
`kb-code` return `code-search-disabled` without spawning; the review's reusability scan is skipped; and the
JetBrains sign-in offer for code search is not made. Because `capabilities.CODE_SEARCH` then reads unavailable,
`gnosis instrument` renders the history-only wiring: `<!--cap:search-code-->` regions drop and
`<!--nocap:search-code-->` regions (what to do instead) stay in the knowledge skill, `gnosis-explorer`,
`gnosis-research` and `gnosis-review`; the gate hooks are written with `GNOSIS_CODE_SEARCH=0`; and the
jbcontext-only pack skills are skipped AND deleted if an earlier install left them. Re-run `gnosis instrument`
after switching (the Air plugin does, through `air.jbcontext.enabled`).

## `gnosis logout`

| Form | Clears |
|---|---|
| `gnosis logout` | the JetBrains session |
| `--github` | the Copilot session; resets a `copilot` provider pin |
| `--anthropic-key` | the stored Anthropic key |
| `--cursor-key` | the stored Cursor key; resets a `cursor` provider pin |
| `--all` | all four, plus `llm_auth_method` and `llm_provider` |

Flags combine; each clears `llm_auth_method` when it named the removed credential. Local removal
only — nothing is revoked server-side. The Cursor CLI's own `agent login` is never touched (it
belongs to the user's Cursor install); `--all` prints that `agent logout` clears it.
