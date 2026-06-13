# diffcog

Prototype CLI for measuring cognitive complexity introduced by Java code changes.

The current implementation analyzes tracked Java changes, maps changed lines to
methods/constructors, and reports custom cognitive complexity deltas.

## Install

```bash
uv tool install --force -e /path/to/diff-complexity
```

Then run `diffcog` from any git repository.

The CLI analyzes the current working directory.

Run the same install command again after dependencies change.

## Usage

Compare `HEAD` against the current working tree:

```bash
diffcog
```

Compare a base ref against the working tree:

```bash
diffcog main
```

Compare two refs:

```bash
diffcog HEAD~1 HEAD
diffcog main HEAD
```

Compare `HEAD` against staged changes:

```bash
diffcog --staged
```

Compare staged changes against unstaged working tree changes:

```bash
diffcog --unstaged
```

Show changed Java files:

```bash
diffcog --details
```

Print JSON:

```bash
diffcog --json
```

Show loaded snapshot metadata:

```bash
diffcog --debug show-snapshots
```

Show parsed Java symbols:

```bash
diffcog --debug show-symbols
```

Show complexity scoring for changed Java methods/constructors:

```bash
diffcog --debug show-complexity
```

Set threshold exits:

```bash
diffcog --max-new 10
diffcog --max-delta 5
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
- Reports custom complexity totals for changed Java methods/constructors.

See [CLI.md](CLI.md) for the CLI contract and [BRAINSTORMING.md](BRAINSTORMING.md)
for design notes.

## Development

Check the codebase:

```bash
uv run diffcog-check
```

Run tests or lint separately:

```bash
uv run pytest
uv run ruff check .
```
