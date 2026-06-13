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
  -> map changed ranges to methods
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
```

Only Java files are analyzed initially.

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

Machine-readable output should require:

```bash
diffcog --json
```

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
diffcog --include 'src/**/*.java'
diffcog --exclude '**/generated/**'
diffcog --diff patch.diff
diffcog --diff -
```

These are intentionally not required for the first CLI shape.
