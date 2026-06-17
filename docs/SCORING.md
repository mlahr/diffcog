# Scoring semantics

diffcog computes complexity for changed callables and reports the delta between
the before and after source states.

```text
introduced complexity = complexity(after) - complexity(before)
```

CK metrics are a separate class-level metric family. They are not cognitive
complexity scores and do not use cognitive complexity rule sets.

Contribution lines explain which rules contributed to a callable score. They are
not a separate scoring model.

## Shared rules

- Control-flow constructs score `1 + current nesting depth`.
- Branch-only constructs such as `else` score `1`.
- Recursion scores `1` once per recursive callable, at the first recursive call line.
- Default rule sets include control flow plus boolean operator chains.
- Control-flow rule sets exclude boolean operator chains.
- Nesting-only constructs increase the nesting depth for contained expressions
  without producing a contribution.

## Java rule sets

```text
java.default       control flow plus boolean operator chains
java.control-flow  control flow only
```

Java control-flow rules:

```text
java.if        if statement
java.else      else branch
java.loop      for, enhanced for, while, do
java.catch     catch clause
java.switch    switch statement or switch expression
java.ternary   ternary expression
java.break     labeled break
java.continue  labeled continue
java.recursion local method recursion
```

`else if` is treated as a continuation of the same conditional chain. It does
not add an extra nesting penalty beyond its own branch score.

Java boolean-chain rule:

```text
java.boolean_chain
```

Boolean-chain scoring counts contiguous `&&` / `||` operator sequences. Switching
between `&&` and `||` starts a new sequence. Unary `!` splits a sequence.
Nested boolean expressions are scored only at the top-most boolean expression
that represents the chain.

Java recursion detection covers local methods reached through direct calls,
`this`, `super`, and class-qualified calls. Calls through other object variables
do not count as local recursion.

Java exclusions and limits:

- Unlabeled `break` and `continue` do not score.
- Method renames are treated as removed plus added callables.
- Initializer blocks and lambdas are not reported as separate callables.

## Python rule sets

```text
python.default       control flow plus boolean operator chains
python.control-flow  control flow only
```

Python control-flow rules:

```text
python.if        if statement
python.elif      elif clause
python.else      else branch
python.loop      for, async for, while
python.except    except clause
python.ternary   conditional expression
python.match     match statement
python.recursion local function or method recursion
```

`elif` is treated as a continuation of the same conditional chain. It does not
add an extra nesting penalty beyond its own branch score.

Lambdas increase nesting for contained expressions, but they do not produce a
separate contribution. `with` / `async with` and comprehension containers also
increase nesting without producing separate contributions.

`match` is scored like Java `switch`: the `match` statement scores once, and
individual `case` clauses do not score.

Python boolean-chain rule:

```text
python.boolean_chain
```

Boolean-chain scoring counts contiguous `and` / `or` operator sequences. Switching
between `and` and `or` starts a new sequence. `not` splits a sequence. Nested
boolean expressions are scored only at the top-most boolean expression that
represents the chain.

Python recursion detection covers local functions and methods reached through
direct calls, `self`, `cls`, and class-qualified calls. Calls through other
object variables do not count as local recursion.

Python exclusions and limits:

- Lambdas are not reported as separate callables and do not score directly.
- `case` clauses, comprehension `for` / `if` clauses, `try else`, and `finally`
  do not score directly.

## CK metrics

`--metrics ck` reports class-level `CBO`, `LCOM`, and `WMC` values for classes in
tracked changed files.

- `WMC` is the count of participating instance methods. Java constructors count;
  Java static methods, Python static methods, and Python class methods do not.
- `LCOM` uses the original CK pair-count definition over participating instance
  methods and the instance fields they access. If every participating method uses
  no instance fields, `LCOM` is `0`.
- `CBO` counts unique statically visible external classes or types coupled to a
  class. Built-in/core types and self references are excluded.

Java `CBO` counts superclass and interface types, field types, parameter types,
return types, thrown types, local variable types, generic type arguments,
annotations, and object creation types.

Python `CBO` counts base classes, annotations, imported constructor-style calls,
and statically nameable `self.field.method(...)` dependencies when the field can
be connected to a visible annotated type. It does not perform type checking or
whole-project import resolution.

## History Metrics

`--metrics history` reports file-level history metrics inspired by Adam
Tornhill's hotspot and change-coupling algorithms. This metric is separate from
callable cognitive complexity deltas and CK class metrics.

Hotspot score:

```text
current file cognitive complexity * recent commit count
```

Current file cognitive complexity is the sum of callable cognitive complexity in
the resolved `after` side of the comparison. Recent commit count comes from the
selected git history window, defaulting to the last 90 days.

Change coupling includes file pairs that changed together in at least two
commits. Coupling percentage is:

```text
shared commits / min(left file commits, right file commits) * 100
```
