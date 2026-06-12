# Diff Cognitive Complexity Brainstorming

## Goal

Build a CLI tool that measures cognitive complexity introduced by a git diff.

Initial focus:

- Java only
- Prototype first
- Custom complexity measure
- Diff-aware before/after comparison
- Attribution matters

Future support for Python is likely, so the parser/tooling choice should not lock the design into Java-only assumptions.

## Core Product Question

The tool should answer:

```text
How much cognitive complexity did this diff introduce?
```

Not:

```text
How complex is this file?
```

The authoritative number should be:

```text
complexity_after - complexity_before = introduced complexity
```

## Current Direction

Use:

```text
Python prototype
Tree-sitter parser
Custom cognitive complexity visitor
Diff-aware delta engine
```

Avoid:

- Writing a Java parser
- Using PMD as the core engine
- Trying to exactly clone Sonar cognitive complexity
- Treating line count as the primary metric

## Why Not PMD As The Core?

PMD is useful for detecting complexity threshold violations, but it may not be the best fit for this product.

The tool needs:

- Raw before/after method-level complexity
- Reliable deltas
- Attribution to constructs introduced by the diff
- A custom metric that reflects our definition of cognitive complexity

PMD may not expose the exact data shape needed, and attribution would likely need to be reconstructed after the fact.

Better approach:

```text
Parse AST -> compute custom score -> emit attribution events during scoring
```

This keeps the score and explanation coming from the same mechanism.

## Parser Choice

Use Tree-sitter as a library, not an external command.

For the prototype:

```text
Python + tree-sitter + tree-sitter-java
```

Tree-sitter provides the Java AST. Our code walks the AST and computes complexity.

Later, Python support can use:

```text
tree-sitter-python
```

## App Shape

Pipeline:

```text
input diff
  -> changed ranges
  -> before/after source
  -> ASTs
  -> symbols
  -> complexity scores
  -> delta report
```

## Layers

### 1. CLI Layer

Thin wrapper.

Responsibilities:

- Read git diff from stdin or file
- Accept options such as `--base`, `--head`, `--format`
- Call the core pipeline
- Print text or JSON output

No analysis logic should live here.

### 2. Diff Layer

Turns a patch into structured changed ranges.

Example model:

```python
ChangedFile(
    path="src/OrderService.java",
    old_path="src/OrderService.java",
    hunks=[
        ChangedRange(old_start=40, old_end=45, new_start=40, new_end=50)
    ],
)
```

Should eventually understand:

- Added files
- Deleted files
- Renamed files
- Modified files

### 3. Source Snapshot Layer

Given changed files, produce source text for both sides.

Example model:

```python
SourcePair(
    path="src/OrderService.java",
    before="...",
    after="...",
)
```

Prototype behavior:

- Before source from `git show base:path`
- After source from working tree or `git show head:path`

This isolates git-specific details.

### 4. Parser Layer

Wraps Tree-sitter.

Input:

```python
source: str
language: "java"
```

Output:

```python
ParsedFile(
    source=source,
    tree=tree_sitter_tree,
)
```

Keep Tree-sitter details contained where practical.

### 5. Symbol Extraction Layer

Finds analyzable Java units.

For Java v1:

- Methods
- Constructors

Later:

- Static initializer blocks
- Instance initializer blocks
- Lambdas, if useful

Example model:

```python
Symbol(
    id="com.acme.OrderService#submitOrder(Order)",
    kind="method",
    name="submitOrder",
    class_path=["OrderService"],
    start_line=35,
    end_line=92,
    node=tree_sitter_node,
)
```

This layer should also map changed ranges to touched symbols.

### 6. Symbol Matching Layer

Pairs before/after symbols.

Example states:

```python
MatchedSymbol(before=old_method, after=new_method)
NewSymbol(before=None, after=new_method)
DeletedSymbol(before=old_method, after=None)
```

Initial matching key:

```text
package + class path + method name + parameter count
```

Renamed methods can initially be treated as delete + add.

### 7. Complexity Engine

This is the product core.

Input:

```python
Symbol node + source
```

Output:

```python
ComplexityResult(
    score=9,
    events=[
        ComplexityEvent(line=42, kind="if", score=1),
        ComplexityEvent(line=43, kind="nested_if", score=2),
    ],
)
```

The engine should be deterministic and easy to test.

Initial rule ideas:

- Branch adds score
- Nesting adds score
- Loops add score
- `catch` adds score
- Boolean chains add score
- Ternary adds score
- `switch` / switch expressions add score

The metric is intentionally custom. It does not need to match Sonar exactly.

### 8. Delta Layer

Compares before/after complexity.

Example model:

```python
SymbolDelta(
    symbol_id="OrderService#submitOrder/1",
    before_score=3,
    after_score=9,
    introduced=6,
    events=[...],
)
```

Important distinction:

- The authoritative number is `after_score - before_score`
- Events explain likely contributors

Events do not need to be perfect arithmetic proof for the entire delta.

### 9. Reporter Layer

Formats results.

Text example:

```text
Complexity introduced: +6

OrderService.submitOrder(): 3 -> 9 (+6)
  +2 nested if at line 43
  +1 catch at line 51
```

JSON example:

```json
{
  "introduced": 6,
  "symbols": []
}
```

## Prototype Folder Shape

```text
diffcog/
  cli.py
  pipeline.py

  diff/
    parser.py
    models.py

  git/
    snapshots.py

  languages/
    java/
      parser.py
      symbols.py
      complexity.py

  analysis/
    matching.py
    delta.py
    models.py

  report/
    text.py
    json.py

tests/
  fixtures/
  test_java_complexity.py
  test_symbol_matching.py
  test_diff_mapping.py
```

## Main Difficulties Still In Scope

### 1. Mapping Diff Hunks To Methods

Risk:

- A changed line may be inside a method, constructor, initializer, lambda, anonymous class, or field initializer.
- Changed braces can make mapping ambiguous.

Mitigation:

- Use Tree-sitter to find the smallest enclosing callable.
- Score at method/constructor level.
- Fall back to class/file level if ambiguous.

### 2. Matching Same Method Before And After

Risk:

- Methods can be renamed.
- Parameters can change.
- Overloads exist.
- Nested classes exist.
- Methods can move within the file.

Mitigation:

- Start with `package + class path + method name + parameter count`.
- Add parameter type extraction if easy.
- Treat unmatched methods as new/deleted.
- Later consider fuzzy body matching.

### 3. Attribution

Risk:

- The delta may be clear while the exact cause is harder to explain.
- Some complexity increases come from interaction between nesting and changed structure, not from a single added line.

Mitigation:

- Emit attribution events during complexity calculation.
- Present events as contributors, not exact causality.
- Keep before/after score delta as the primary truth.

### 4. Defining The Metric

Risk:

- Custom scoring can become arbitrary if not kept simple and explainable.

Mitigation:

- Keep the first rule set small.
- Test rules with focused Java snippets.
- Make output show the constructs that contributed.

## Prototype Acceptance Target

The first useful prototype should handle:

```bash
git diff main...HEAD | diffcog --lang java
```

And output something like:

```text
Complexity introduced: +7

OrderService.submitOrder(): 3 -> 10 (+7)
  +2 nested if at line 42
  +1 catch at line 49
  +1 boolean chain at line 53
```

## Current Working Assumption

Computing custom cognitive complexity from an AST is feasible.

It is much easier than writing a Java parser, and it gives us first-class attribution.

Estimated effort for Java-only prototype:

```text
Basic scoring: 2-4 days
Good implementation with tests: 1-2 weeks
Sonar-compatible edge cases: not a goal
```
