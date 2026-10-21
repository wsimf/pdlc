# PDLC attachments

PDLC attachments are local-only artifacts. A post script copies each supplied
file into `.pdlc/{work-item-number}/attachments` and records it in the local
`files.json`; nothing is added to the GitHub Issue, Project, or file Work Item
backend.

This includes local files the driver supplied in the prompt, such as mockups
or screenshots. `--attachment` takes a filesystem path, so write any pasted
image to a local path before passing it.

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

`pdlc prompt product-writer` takes the same `--attachment` options before anything is posted: it records each file for the Product draft until it lands, lists it in every brief on the draft, and puts it on the land command it names. It reads the file from its path at landing, so keep it there until then.
