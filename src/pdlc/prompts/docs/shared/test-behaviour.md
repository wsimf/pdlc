## Test behaviour, not implementation

A test calls the code the way its users do and asserts the result they observe
against a literal expected value. A test that asserts which calls the code
made, or restates a constant the code contains, does neither.

Before you keep a test, ask whether it would still pass if every function it
imports returned nothing (`undefined`, `None`, `nil`). If it would, it observes
no behaviour and cannot fail for a defect. Rewrite the assertion or delete the
test.

Five shapes that still pass when the code returns nothing:

- **Weak or no assertion.** No assertion at all, or only "is defined", "is
  truthy", "does not throw", "is an instance of", or "is greater than zero".
- **Mock or absence only.** Only "was called", "was not called", "is empty",
  "is nil", or "is not this wrong value".
- **Self-referential.** The expected value comes from the code under test:
  `f(a) == f(a)`, `parsed.url == build_url(...)`.
- **Constant pin.** The assertion restates a hand-maintained constant, config
  default, table row, or prompt string: `LIMITS.max_tools == 8`.
- **Fixture asserts fixture.** The assertion reads data the test built itself,
  and the subject never runs inside the test body.

The fix: call the subject inside the test body with one concrete input and
assert the literal output or the observable effect:
`slugify("Hello, World!") == "hello-world"`. For an absence, assert the
presence on another input in the same test. For a constant, test the mechanism
that reads it with one input instead of restating the value. For a mock, assert
the payload it received or the state after the call, not that it was called.
When no such assertion exists, delete the test and report the behaviour as a
testability limitation.

Keep a test of a relation across a table's rows (a key present in two tables,
a parent that exists), and a compile-time type check.
