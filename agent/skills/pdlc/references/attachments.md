# PDLC attachments

PDLC attachments are local-only artifacts. A post script copies each supplied
file into `.pdlc/{work-item-number}/attachments` and records it in the local
`files.json`; nothing is added to the GitHub Issue, Project, or file Work Item
backend.

Pass each file with `--attachment`. An optional description must immediately
follow the attachment it describes:

```bash
--attachment /tmp/navigation.png \
--attachment-description "Primary navigation mockup" \
--attachment /tmp/empty-state.png
```

Descriptions are optional. Inspectors show the supplied description or fall
back to the saved filename, followed by the resolved local path. The same
`--attachment` option can be repeated for multiple files.
