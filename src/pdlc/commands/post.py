"""Post-command registry.

Individual stage implementations live beside this module so each command
retains its existing validation and evidence contract.
"""

POST_COMMANDS = (
    "approve", "ci", "complete", "decision", "implement", "implement-task",
    "invalidate", "plan", "review", "skip", "tasks", "test", "verify", "write",
)
