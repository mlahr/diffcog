# diffcog

Measure cognitive complexity introduced by code changes.

`diffcog` is a prototype command-line tool for reviewing how a change affects
method-level cognitive complexity. It compares two Git-backed code states,
parses the changed tracked Java, Python, and Go files, maps changed line ranges to
callables, and reports before/after complexity deltas.

The goal is to make complexity review fit naturally into local development and
CI: compare a branch, staged change, working tree, or pair of refs, then fail
the run when the introduced complexity crosses a configured threshold.

## What it reports

- New complexity introduced by added or more complex callables.
- Removed complexity from deleted or simplified callables.
- Net complexity delta between the before and after states.
- Optional changed-file details and top changed-callable hotspots.
- Optional CK class metrics: `CBO`, `LCOM`, and `WMC`.
- Optional history metrics: file-level hotspots and change coupling.
- Optional JSON output for automation.

## Current scope

`diffcog` currently analyzes tracked `.java`, `.py`, and `.go` files. Untracked files are
ignored. Java, Python, and Go are implemented through separate language adapters,
with `auto` mode running all adapters in one command.

This repository is still a prototype. The CLI contract is documented in
[CLI.md](CLI.md), and scoring semantics are documented in
[docs/SCORING.md](docs/SCORING.md).

## Installation

Install from a local checkout with `uv`:

```bash
uv tool install --force -e /path/to/diffcog
```

After installation, run `diffcog` from inside any Git repository:

```bash
diffcog
```

Run the install command again after dependency or entry-point changes.

## Basic usage

Compare `HEAD` against the current working tree:

```bash
diffcog
```

Compare a base ref against the current working tree:

```bash
diffcog main
```

Compare two explicit refs:

```bash
diffcog HEAD~1 HEAD
diffcog main HEAD
```

Compare `HEAD` against staged changes only:

```bash
diffcog --staged
```

Compare the index against unstaged working tree changes:

```bash
diffcog --unstaged
```

## Comparison semantics

`diffcog BASE TARGET` means:

```text
before = BASE
after  = TARGET
introduced complexity = complexity(after) - complexity(before)
```

`diffcog BASE` means:

```text
before = BASE
after  = working tree
```

`diffcog` means:

```text
before = HEAD
after  = working tree
```

When both refs are explicit, uncommitted changes are ignored.

## Output modes

Show changed analyzed files:

```bash
diffcog --details
```

Show top changed-callable complexity hotspots:

```bash
diffcog --hotspots
```

Print machine-readable JSON:

```bash
diffcog --json
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

## Languages and rule sets

Auto mode is the default. It analyzes changed tracked Java, Python, and Go files in
the same run, using each language adapter's default rule set.

Select a language:

```bash
diffcog --language java
diffcog --language python
diffcog --language go
```

Select a built-in rule set:

```bash
diffcog --language java --ruleset java.default
diffcog --language java --ruleset java.control-flow
diffcog --language python --ruleset python.default
diffcog --language python --ruleset python.control-flow
diffcog --language go --ruleset go.default
diffcog --language go --ruleset go.control-flow
```

List available rule sets:

```bash
diffcog --list-rulesets
```

`--ruleset` requires an explicit `--language java`, `--language python`, or `--language go`.
Auto mode always uses each language adapter's default rule set.

## Path filtering

Limit analysis to matching changed paths:

```bash
diffcog --include 'src/main'
diffcog --include 'src/**/*.java'
diffcog --exclude '**/generated/**'
diffcog --include 'src' --exclude '**/generated/**'
```

`--include` and `--exclude` use Git pathspec syntax and may be repeated.
Path filters do not expand language scope; only tracked files supported by the
active language mode are analyzed.

## Alternate metrics

Show CK class metrics:

```bash
diffcog --metrics ck
diffcog --metrics ck --json
```

`--metrics ck` reports `CBO`, `LCOM`, and `WMC` before/after/delta values for
classes in tracked changed Java and Python files, and for struct/interface types
in tracked changed Go files.

Show history metrics:

```bash
diffcog --metrics history
diffcog --metrics history --history-days 30
diffcog --metrics history --json
```

`--metrics history` reports recent file-level hotspots and change coupling.
By default, history mining uses the last 90 days.

Alternate metrics are separate report modes. They do not use complexity rule
sets, and complexity thresholds do not apply to them.

## Debug reports

Show loaded source snapshot metadata:

```bash
diffcog --debug show-snapshots
```

Show parsed callable symbols:

```bash
diffcog --debug show-symbols
```

Show complexity scoring for changed callables:

```bash
diffcog --debug show-complexity
```

Debug modes are intended for development and troubleshooting. They do not print
full source content.

## Development

Run the full project check:

```bash
uv run python -m diffcog.check
```

Run tests or lint separately:

```bash
uv run python -m pytest
uv run ruff check .
```
