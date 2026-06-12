# diffcog

Prototype CLI for measuring cognitive complexity introduced by Java code changes.

The current implementation has the CLI and git comparison plumbing in place. The
complexity analyzer is still a placeholder and reports zero scores.

## Install

Use `uv` from the repository root:

```bash
uv sync
```

Run the CLI:

```bash
uv run diffcog
```

## Usage

Compare `HEAD` against the current working tree:

```bash
uv run diffcog
```

Compare a base ref against the working tree:

```bash
uv run diffcog main
```

Compare two refs:

```bash
uv run diffcog HEAD~1 HEAD
uv run diffcog main HEAD
```

Compare `HEAD` against staged changes:

```bash
uv run diffcog --staged
```

Compare staged changes against unstaged working tree changes:

```bash
uv run diffcog --unstaged
```

Show changed Java files:

```bash
uv run diffcog --details
```

Print JSON:

```bash
uv run diffcog --json
```

Set threshold exits:

```bash
uv run diffcog --max-new 10
uv run diffcog --max-delta 5
```

Exit codes:

```text
0 = success and thresholds passed
1 = usage or runtime error
2 = threshold failed
```

## Current Scope

- Tracks `.java` files only.
- Uses git refs, index, and working tree states as inputs.
- Excludes untracked files for now.
- Reports placeholder complexity totals until the analyzer is implemented.

See [CLI.md](CLI.md) for the CLI contract and [BRAINSTORMING.md](BRAINSTORMING.md)
for design notes.

## Development

Run tests:

```bash
uv run pytest
```

Run lint:

```bash
uv run ruff check .
```
