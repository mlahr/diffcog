# Scoring semantics

diffcog computes complexity for changed callables and reports the delta between
the before and after source states.

```text
introduced complexity = complexity(after) - complexity(before)
```

Contribution lines explain which rules contributed to a callable score. They are
not a separate scoring model.

## Shared rules

- Control-flow constructs score `1 + current nesting depth`.
- Branch-only constructs such as `else` score `1`.
- Recursion scores `1` once per recursive callable, at the first recursive call line.
- Default rule sets include control flow plus boolean operator chains.
- Control-flow rule sets exclude boolean operator chains.

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
python.case      case clause
python.with      with, async with
python.try_else  try else branch
python.finally   finally branch
python.comprehension_for  comprehension for clause
python.comprehension_if   comprehension if clause
python.recursion local function or method recursion
```

`elif` is treated as a continuation of the same conditional chain. It does not
add an extra nesting penalty beyond its own branch score.

Lambdas increase nesting for contained expressions, but they do not produce a
separate contribution. Comprehension containers also increase nesting; their
hidden `for` and `if` clauses are the scored decision points.

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
