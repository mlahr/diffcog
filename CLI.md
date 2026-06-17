# diffcog CLI

## Primary Model

`diffcog` compares two code states and reports cognitive complexity introduced by the second state.

Primary comparison forms:

```bash
diffcog BASE HEAD
```

Compare one git ref against another.

```bash
diffcog BASE
```

Compare `BASE` against the current working tree.

```bash
diffcog
```

Compare `HEAD` against the current working tree.

Working tree comparisons include staged and unstaged changes by default.

## Examples

Compare the previous commit to the current commit:

```bash
diffcog HEAD~1 HEAD
```

Compare `main` to the current commit:

```bash
diffcog main HEAD
```

Compare `main` to the working tree:

```bash
diffcog main
```

Compare `HEAD` to the working tree:

```bash
diffcog
```

Compare `HEAD` to the staged changes only:

```bash
diffcog --staged
```

Compare the index to unstaged changes only:

```bash
diffcog --unstaged
```

Select a language or built-in rule set:

```bash
diffcog --language java
diffcog --language python
diffcog --language java --ruleset java.default
diffcog --language python --ruleset python.control-flow
```

List available rule sets:

```bash
diffcog --list-rulesets
```

Show CK class metrics:

```bash
diffcog --metrics ck
diffcog --metrics ck --json
```

Show Tornhill-style history metrics:

```bash
diffcog --metrics history
diffcog --metrics history --history-days 30
diffcog --metrics history --json
```

Limit analysis to matching paths:

```bash
diffcog --include 'src/main'
diffcog --include 'src/**/*.java'
diffcog --exclude '**/generated/**'
diffcog --include 'src' --exclude '**/generated/**'
```

## Semantics

The command:

```bash
diffcog BASE TARGET
```

means:

```text
before = BASE
after  = TARGET
introduced complexity = complexity(after) - complexity(before)
```

The command:

```bash
diffcog BASE
```

means:

```text
before = BASE
after  = working tree
introduced complexity = complexity(working tree) - complexity(BASE)
```

The command:

```bash
diffcog
```

means:

```text
before = HEAD
after  = working tree
introduced complexity = complexity(working tree) - complexity(HEAD)
```

The command:

```bash
diffcog --staged
```

means:

```text
before = HEAD
after  = index
```

The command:

```bash
diffcog --unstaged
```

means:

```text
before = index
after  = working tree
```

The tool should print the resolved comparison clearly:

```text
Comparing HEAD -> working tree
```

or:

```text
Comparing main -> HEAD
```

When two explicit refs are provided, the working tree is ignored:

```bash
diffcog main HEAD
```

means exactly:

```text
before = main
after  = HEAD
```

Uncommitted changes do not affect that result.

## Rule Sets

The default language mode is:

```text
auto
```

Auto mode analyzes Java and Python changes in one run and uses each language's
default rule set:

```text
java.default
python.default
```

Built-in Java rule sets:

```text
java.default       control flow plus boolean operator chains
java.control-flow  control flow only
```

Built-in Python rule sets:

```text
python.default       control flow plus boolean operator chains
python.control-flow  control flow only
```

Unknown rule set names are usage errors.

`--ruleset` may only be used with an explicit `--language java` or
`--language python`. Auto mode always uses each language's default rule set.

`--list-rulesets` prints available rule set IDs and exits without reading git state.
By default it lists all supported languages. With `--language java` or
`--language python`, it lists only that language's rule sets.

See [docs/SCORING.md](docs/SCORING.md) for scoring semantics.

## CK Metrics

`--metrics ck` switches the report from callable cognitive complexity to
class-level CK metrics. It reports `CBO`, `LCOM`, and `WMC` before/after/delta
values for classes in tracked changed files.

CK metrics are separate from cognitive complexity rule sets. `--metrics ck`
does not use `--ruleset`, does not affect complexity thresholds, and is not a
debug mode.

`--metrics ck` can be used with `--language auto`, `--language java`, or
`--language python`. Auto mode reports Java and Python classes in changed
tracked `.java` and `.py` files.

`--metrics ck` cannot be combined with `--details`, `--hotspots`, `--debug`,
`--list-rulesets`, or `--ruleset`.

## History Metrics

`--metrics history` switches the report from callable cognitive complexity to
file-level history metrics inspired by Adam Tornhill's hotspot and
change-coupling analyses.

This is a separate history-mining report. It is not a model migration, API
dependency removal, projection removal, or class rename.

History metrics include:

```text
hotspots         recent churn weighted by current cognitive complexity
change coupling file pairs that frequently change together
```

By default, history mining uses the last 90 days. Use `--history-days` to change
the window:

```bash
diffcog --metrics history --history-days 30
```

The history report respects `--language`, `--include`, and `--exclude`. With
`--language auto`, Java and Python tracked files are included.

Hotspot scoring is file-level:

```text
hotspot score = current file cognitive complexity * recent commit count
```

Current file cognitive complexity is computed from the resolved `after` side of
the comparison. History traversal is anchored at the target ref when the `after`
side is a ref, and at `HEAD` for index or working-tree comparisons. Merge commits
are included.

Change coupling reports file pairs with at least two shared commits. Coupling
percentage is:

```text
shared commits / min(left file commits, right file commits) * 100
```

`--metrics history` is separate from complexity thresholds. `--max-new` and
`--max-delta` do not apply to history metrics.

`--history-days` may only be used with `--metrics history`.

`--metrics history` cannot be combined with `--details`, `--hotspots`, `--debug`,
`--list-rulesets`, or `--ruleset`.

## Path Filters

`--include` and `--exclude` use git pathspec syntax.

Both options may be repeated:

```bash
diffcog --include 'src/main' --include 'src/test'
diffcog --exclude '**/generated/**' --exclude 'legacy'
```

When no include is provided, all changed tracked files for the selected language
mode are candidates. Auto mode includes tracked `.java` and `.py` files.

When one or more includes are provided, only changed files matching those
pathspecs are candidates.

Excludes are applied after includes.

Path filters do not expand language scope. Even if an include pathspec matches
files outside the active language adapter, only tracked files for that adapter
are analyzed. Auto mode analyzes tracked `.java` and `.py` files only.

## Why Not Raw Diff As The Main Input?

A raw unified diff identifies changed files and changed line ranges, but it does not provide enough context to compute method-level cognitive complexity reliably.

The analyzer needs complete source for both sides:

```text
before source = full file content at BASE
after source  = full file content at TARGET or working tree
```

So `diffcog` should own the git plumbing:

```text
resolve comparison
  -> get changed files
  -> load before/after source snapshots
  -> parse ASTs
  -> map changed ranges to callables
  -> compute before/after complexity
  -> report delta
```

Raw diff input can be added later as a secondary mode:

```bash
git diff main...HEAD | diffcog --diff -
```

But it should not be the primary interface.

## Initial Scope

For the prototype, support:

```bash
diffcog BASE HEAD
diffcog BASE
diffcog
diffcog --staged
diffcog --unstaged
diffcog --include PATHSPEC
diffcog --exclude PATHSPEC
```

Java and Python files are analyzed initially, through language adapters.

Text output is the default.

File status behavior, such as added, deleted, renamed, and modified files, belongs below the CLI layer and is intentionally postponed.

## Thresholds

Thresholds control exit status.

```bash
diffcog --max-new 10
diffcog main HEAD --max-new 10
diffcog main HEAD --max-delta 5
```

`--max-new` applies to newly introduced positive complexity.

`--max-delta` applies to the net complexity delta.

Exit codes:

```text
0 = completed successfully and thresholds passed
1 = usage or runtime error
2 = completed successfully but a threshold failed
```

## Output Shape

The output shape still needs design work.

Current working concepts:

```text
new complexity = positive complexity introduced by added/increased methods
removed complexity = complexity removed by deleted/decreased methods
net delta = new complexity - removed complexity
```

Threshold mapping:

```text
--max-new applies to new complexity
--max-delta applies to net delta
```

Example:

```text
Comparing HEAD~1 -> HEAD

New complexity: +7
Removed complexity: -0
Net delta: +7

OrderService.submitOrder(): 3 -> 10 (+7)
  +2 nested if at line 42
  +1 catch at line 49
  +1 boolean chain at line 53
```

The main number is the before/after delta:

```text
after_score - before_score
```

Attribution events explain likely contributors.

They are supporting evidence, not the source of truth for the final delta.

Default text output should be concise.

Detailed attribution should require:

```bash
diffcog --details
```

Hotspot output should require:

```bash
diffcog --hotspots
```

`--hotspots` prints the normal summary plus up to 10 changed methods or
constructors with nonzero complexity deltas. Hotspots are sorted by biggest
absolute complexity change first. Each hotspot includes a shortened unique file
suffix and start line, callable name, callable kind, before and after complexity,
signed delta, and at most one top changed-line rule hint.

`--details` and `--hotspots` are mutually exclusive.

Machine-readable output should require:

```bash
diffcog --json
```

`--json --hotspots` keeps the normal JSON shape.

The exact schemas and text layout are still open.

## Debug Modes

Show loaded before/after source snapshot metadata:

```bash
diffcog --debug show-snapshots
diffcog main HEAD --debug show-snapshots
diffcog --staged --debug show-snapshots
diffcog --unstaged --debug show-snapshots
```

This prints presence, line count, and byte count for each changed Java file.
It does not print full source content.

Show parsed Java symbols:

```bash
diffcog --debug show-symbols
diffcog main HEAD --debug show-symbols
diffcog --debug show-symbols --json
```

This parses loaded Java snapshots and prints extracted methods and constructors.
It does not print the full AST.

Show complexity scoring for changed Java methods and constructors:

```bash
diffcog --debug show-complexity
diffcog main HEAD --debug show-complexity
diffcog --debug show-complexity --json
```

## Later Options

Potential options after the first prototype:

```bash
diffcog --lang java
diffcog --diff patch.diff
diffcog --diff -
```

These are intentionally not required for the first CLI shape.
