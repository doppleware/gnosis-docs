<!-- Mirrored from the gnosis source repository by scripts/sync_public_docs.py — edit it there. -->

# What changes on your machine: `gnosis instrument` and opening a folder in Air

Two things write into your coding-agent environment: running `gnosis instrument`, and opening
a folder with the Air extension active. This page lists every change either one makes, where
it lands, which agents read it, and why it is there. It is written for the person whose
machine and repository are being instrumented.

Companion pages: [install-flow.md](install-flow.md) covers the sign-in and component install, and
`gnosis instrument --help` lists every flag (the full per-scope reference is gnosis-instrument.md).

## The short version

- **Your git history is never touched.** Every file written into a repository is new,
  gnosis- or Air-owned, and listed in the repository's `.git/info/exclude`. `git status` stays
  clean, and nothing machine-specific can be committed by accident.
- **Agents get one instruction**: look the task up in the knowledge base before grepping. The
  rest of the files teach them how, let it run without permission prompts, and keep the
  knowledge base current.
- **Air adds its worktree workflow**: a tool, a skill, three hooks and a block of text that
  tell the agent which isolation scope a session runs in.
- **Removal is complete and symmetric**, except for two shared items noted at the end.

## 1. Opening a folder in Air

On activation the extension does the following, in this order. Nothing here asks you first,
except the first-run wizard.

### First run only: the component install

The wizard signs you in to JetBrains and runs `gnosis install`. That installs the tools the
agents will call, outside any repository:

| What | Where | Why |
|---|---|---|
| `gnosis` | a `uv` tool from the extension's bundled wheel, on your `PATH` | The knowledge CLI and the analysis pipeline. |
| `jbcontext` | `~/.jbcontext`, shim in `~/.local/bin` | Semantic code search over the repository. |
| `chatter` | `~/.gnosis/bin` | Reads agent transcripts and attributes edited lines to the conversation that wrote them. |
| `embark-call-graph` | a `uv` tool, state in `~/.embark-call-graph` | The call-graph index behind the flow commands and the review's impact analysis. Runs a daemon. |
| your LLM choice | gnosis settings, credentials in `~/.gnosis` or the keychain | The analysis pipeline needs an LLM; this is where its credential lives. |

Air waits for this to finish before instrumenting any repository, because instrumenting earlier
would advertise commands whose backends were not on disk yet.

### Every activation: per-project instrumentation

For every folder in the window, Air runs `gnosis instrument <folder>`. Section 2 lists what that
writes. This is what starts the watcher and keeps the knowledge base current, so it runs
regardless of the "Instrumentation Scope" setting.

### Every activation: Air's own agent wiring

Written at the "Instrumentation Scope" (default: into the project; "Every project" writes the
same into `~/.claude`).

**The worktree tool.** `~/.air/bin/air-worktree`, a bash script, plus a `jq` binary downloaded
into `~/.air/bin` when none is on your `PATH`. It creates and joins git worktrees so that each
coding task has its own branch and Air can track it. Machine-wide, because hooks and skills
reference it by this path.

**The `air-worktree` skill.** `.claude/skills/air-worktree/SKILL.md`. Documents the tool and the
rule: create a worktree before the first edit of a coding task, work inside it, join an existing
one when asked.

**Three hooks.** Scripts in `.claude/hooks/air-worktree-*.sh`, registered in
`.claude/settings.local.json` (or `~/.claude/settings.json` at user level):

| Hook | Runs | Does |
|---|---|---|
| UserPromptSubmit | every prompt | In a session an Air chat started, tells the agent its isolation scope (worktree, current branch, or agent decides) and lists the worktrees it holds. This is the "Isolation scope for this session" line at the top of each turn. In a session Air did not start, such as Claude Code in a terminal, it says nothing unless that session created a worktree on request. |
| PreToolUse | before a shell command or an edit | Records a pending link when the agent creates, joins or adopts a worktree, so the conversation is linked even if the tool's output is cut short. In a session Air started under worktree isolation, denies an edit to the main checkout until the session has a worktree for that repository. A session Air did not start is never denied and never addressed. Fails open whenever it cannot be sure the rule applies. |
| PostToolUse | after a shell command | Reads the create or join result, records the worktree in the session's state and writes the link the Sessions panel shows. Never blocks. It acts only on a command whose command word is the tool itself; a grep or a commit message that merely mentions "create" no longer triggers it. |

**A "Worktrees and isolation scope" block** in `CLAUDE.local.md` (marked
`<!-- BEGIN AIR worktrees -->`), explaining the three scopes in prose for agents, including
what to do when the session already runs inside a worktree another tool made: register it
with `air-worktree adopt` rather than creating a second one.

**Cursor worktrees** (setting "Cursor worktrees" in the Settings tab, `air.worktrees.cursor`,
default auto). Cursor runs its agents in worktrees of its own, under `~/.cursor/worktrees`,
and never runs the hooks above. When Air detects Cursor (the host is Cursor, Cursor already has
worktrees for this repository, or the Cursor CLI is installed) it writes:

| What | Where | Why |
|---|---|---|
| a worktree setup script | `.cursor/worktrees.json` names `.cursor/hooks/air-worktree-setup.sh` | Cursor runs it inside every worktree it creates, and it registers that worktree with Air. Nothing is created; Cursor's checkout stays where Cursor put it. |
| a `sessionStart` hook | `.cursor/hooks.json` and `.cursor/hooks/air-worktree-session-start.sh`, and the same in `~/.cursor/` | When a Cursor session opens inside a worktree of an instrumented repository, the hook registers it and tells the agent it is already in an Air worktree. It also hands the agent the main checkout's `CLAUDE.local.md`: a new worktree holds only committed files, so without this the session would see none of the prompt. |

The copy in `~/.cursor` is the one that reaches sessions inside a Cursor worktree, since the
project copy does not exist there. The hook does nothing in a main checkout or in a repository
Air does not instrument. A `worktrees.json` or `hooks.json` your team committed, or one you
wrote yourself, is never modified; Air logs the line to add instead. Setting the option to
"Off" removes everything Air wrote here.

**The Code Flows wiring**, only once a call graph exists for the repository: a `code-flows`
skill under `.claude/skills/` and a "Code Flows (call graph)" block in `CLAUDE.local.md`. They
teach two commands: show the flows a line of code takes part in, and search flows by
description. Tracing callers by grep is slow and unreliable; the index is already built.

**An `air` block in `.git/info/exclude`** listing the paths above, so none shows in `git
status`.

### Every activation: the `.gnosis/` folder

Air makes sure `.gnosis/` is ignored in every open repository, through `.git/info/exclude`.
Reviews, diagrams and change models are written there, per branch, often several megabytes.

### State Air keeps in `~/.air`

| Folder | What |
|---|---|
| `bin/` | the worktree tool and a downloaded `jq` |
| `worktrees/<repo>/` | the registry of Air worktrees: metadata, conversation links. Worktrees Cursor made and Air adopted are here too, marked as adopted; removing one from Air only unregisters it |
| `isolation/<session>.json` | the isolation scope each chat chose when its task started |
| `pending-links/` | the hand-off between the PreToolUse hook and the tool |
| `assistant-mode/` | the per-session Assistant Mode flag |

## 2. Running `gnosis instrument`

Run by Air for every open folder, or by you. Default scope is the project; `--user` writes the
equivalent into `~/.claude`, `~/.codex` and `~/.copilot` for every repository.

### The knowledge prompt

A short block under a "Codebase knowledge (gnosis)" heading, between
`<!-- BEGIN gnosis-knowledge -->` and `<!-- END gnosis-knowledge -->`.

| File | Read by | Note |
|---|---|---|
| `CLAUDE.local.md` | Claude Code, Cursor | Claude Code's machine-local memory file, loaded next to `CLAUDE.md`. Your own notes outside the markers are kept. |
| `.cursor/rules/gnosis-knowledge.mdc` | Cursor | The same text as an always-applied rule. Cursor reads `CLAUDE.md` before `CLAUDE.local.md`, and in a repository with a long `CLAUDE.md` the prompt sat too deep to be noticed. |
| `.github/copilot-instructions.md` | GitHub Copilot | Copilot's repository instructions, read first. If your repository already commits this file, the prompt goes to `.github/instructions/gnosis-knowledge.instructions.md` instead. |
| `~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`, `~/.copilot/copilot-instructions.md` | Claude Code, Codex, Copilot | `--user` only. Codex has no project-local file, so this is the only way it gets the prompt. |

**What it says.** Before any grep, read, edit or subagent, run one knowledge lookup phrased as
the task. Then: what to do inside an Air worktree, how to delegate to the explorer subagent,
and the commands available on this machine.

**Why.** Models do not reach for a knowledge base on their own. In headless sessions, a prompt
that said "prefer gnosis over grep" produced a lookup in 5 of 32 runs; one that made the lookup
a concrete first step produced 32 of 32. The wording is tested before every change and carries
a version stamp.

**Why it spells a full path.** An IDE launched from the macOS Dock has no `~/.local/bin` on its
`PATH`, so a bare `gnosis` failed there. The full path is also why the file must stay local.

**Why the command list varies.** Code search needs `jbcontext` and the flow commands need
`embark-call-graph`. A command whose backend is missing is left out. Re-run instrument after
installing one.

### Skills

Markdown files under `.claude/skills/<name>/SKILL.md`, read by Claude Code, Cursor and the
Copilot CLI. The front-matter description says when a skill applies; the body is loaded only
when it is used, so skills cost nothing until then.

| Skill | Teaches | Why |
|---|---|---|
| `gnosis-knowledge` | The `gnosis knowledge` commands and how to follow the ready-to-run links in their results. | The prompt says "look it up"; this is how. |
| `gnosis-search` | Searching earlier conversations' topics and decisions in this project. | Project scope only; it bakes the project path in. |
| `gnosis-research` | Exploring unfamiliar code: semantic search plus the recorded history of what is found. | "How does X work" before a change. |
| `gnosis-review` | Reviewing a change with each changed file's history. | Reviewing a branch, judging blast radius. |
| `gnosis-org-search`, `gnosis-dependency-search`, `gnosis-blast-radius` | Searching across many repositories. | Experimental; installed only when `jbcontext` is present, since they delegate to it. |

At user level the skills are also copied into `~/.copilot/skills`, the only place the Copilot
CLI reads personal skills from.

### The gnosis-explorer subagent

`.claude/agents/gnosis-explorer.md`: a subagent limited to running commands and reading files.
It runs the knowledge lookups in its own context and returns a short report with file
locations, decisions, prior tasks and citations, which keeps the JSON out of the main
conversation. Copilot gets a second copy at `.github/agents/gnosis-explorer.agent.md` without
the model pin, because it read the pinned model name literally and failed on every first spawn.

### The `/new-task` command

`.claude/commands/new-task.md`. Typing `/new-task` makes the agent emit a hand-off that Air turns
into a new tracked task, with the files, line numbers and findings the next agent needs.

### Settings entries

Into `.claude/settings.local.json` in the project, or `~/.claude/settings.json` with `--user`.
Only gnosis's own entries are touched.

| Entry | Why |
|---|---|
| `permissions.allow`: `Bash(gnosis knowledge:*)` and the full-path form | Otherwise Claude Code asks you to approve the lookup the prompt just told the agent to run, every time. |
| `sandbox.excludedCommands`: `gnosis`, `jbcontext`, `embark-call-graph` | Claude Code's Bash sandbox blocks the socket `jbcontext` authenticates through, which turned every code search into a silent failure. Inert until you turn the sandbox on. |
| `--hooks` only: three `air-gnosis-*.sh` hook registrations | See "Knowledge gates" below. |

### The trust flag

The project is marked trusted in `~/.claude.json`. Headless runs of Claude Code never show the
trust dialog, and an untrusted project ignores `settings.local.json`, which would disable
everything above. This is the one write outside the repository that `--remove` leaves in place.

### Knowledge gates (off by default)

`gnosis instrument --hooks` adds three scripts that remind the agent of the knowledge base on
every prompt, deny broad searches and the first edit of existing code until a lookup has run,
and track that state. The Air setting that would pass `--hooks` is off. Agents follow the
prompt without being forced: nearly every session in the live store this week ran its lookup
first, and a denied tool costs a turn. With the gates on, the knowledge skill gains a paragraph
describing them.

### A warning when the team starts tracking one of these files

If a teammate commits a path Air wrote locally, such as `.github/copilot-instructions.md` or
`.cursor/hooks.json`, your next pull would stop with "untracked working tree files would be
overwritten". Instrument checks the upstream branch and prints the file and the two steps that
resolve it before that happens.

### The `gnosis` block in `.git/info/exclude`

Every path above, plus `.gnosis/`, in one marked block. Rewritten in place on every run; the
rest of the file is yours.

### The watcher

Project scope starts a `gnosis watch` daemon for the repository. It ingests, classifies and
analyzes conversations as they land on disk, which is what fills the knowledge base. Its pidfile
and log are under `~/.gnosis/watch/`; the store itself is at `~/.local/share/gnosis/`. It also
registers the repository with the call-graph daemon when one is installed. `--user` starts
nothing.

### Legacy cleanup

Earlier builds wrote the prompt into the committed `CLAUDE.md` or `AGENTS.md`. Instrument now
removes that block when doing so restores the file to what is committed. A block your team
committed is left alone, with a note to remove it in a commit of your own.

## 3. Only when you use a feature

These are not part of activation or instrumentation, but they do write into the repository:

- **Reviews, diagrams and change models** go under `.gnosis/` (ignored, see above).
- **"Walk in editor"** can export a CodeTour file into `.tours/` when you ask it to.

## 4. Removing it

| Command | Undoes |
|---|---|
| `gnosis instrument --remove` | the project-level files, the settings entries, the watcher |
| `gnosis instrument --user --remove` | the user-level files, including the legacy `~/.claude/settings.local.json` older builds wrote |
| Air: "Remove all agent instrumentation" | both of the above plus the worktree and code-flows wiring at both scopes, and the Cursor files in each project and in `~/.cursor` |
| Air: "Remove gnosis components" | the installed tools and credentials; data stays |
| Air: "Delete local data" | the conversation store and caches |

Kept on purpose: the call-graph registration, because it is shared by every tool on the
machine; the `.gnosis/` exclude entry, because reviews already on disk live there; the trust
flag in `~/.claude.json`; and existing Air worktrees, which stay usable.
