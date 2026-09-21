## Sequencing the tasks

Tasks land in order, each on its own pull request stacked on the one before, so
the order of the tree is the order a reviewer reads the change. Sequence it so
the stack proves itself.

- **Each task ends in a state you can check.** Its acceptance criteria hold on
  its own pull request, before any later task lands. A criterion only a later
  task can satisfy belongs to that later task.
- **Scaffold first.** A contract every later task consumes — a shared model, a
  boundary, an error vocabulary — lands in the earliest task that needs it, not
  re-described across several. Ask of each early task: does every task after it
  benefit from this existing?
- **Each task lands one coherent capability** or deepens one that already
  exists. Do not spread a capability across tasks as special-case pieces that
  only work once all of them land.
- **Subtract before you add.** When the requirements replace existing
  behaviour, retiring the old behaviour is part of the tree, not a follow-up:
  order the removal first when it simplifies what follows, or put it in the same
  task as its replacement. Never leave a tree that ships the old and new paths
  side by side.
- **Migrate, then delete.** When a requirement moves callers to a new contract,
  the same wave moves every caller and removes the old contract. A compatibility
  path survives only when a requirement or constraint names an external
  consumer that needs it.
