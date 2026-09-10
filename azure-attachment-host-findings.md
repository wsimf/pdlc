# Azure DevOps attachments as a PDLC attachment host

Goal: assess whether Azure DevOps Boards can back the `[attachment_host]` seam, the way `azure-devops-boards-backend.md` did for the work-item backend.

**Status: feasible, validated live, not yet built.** Everything marked ✓ was run against `https://dev.azure.com/madushan92`, project `pdlc-scratch`, work item #20. Probe attachments were left in place for inspection.

## Verdict

The Azure DevOps attachment REST resource supports the full round trip the `AttachmentHost` port needs — upload, list-back off the work item, and byte-identical download. ✓
Adoption is blocked on three decisions, none of them a backend limitation:

1. **The `az` CLI cannot upload binary.** A new dependency or an SDK shim is required.
2. **The port contract returns a local filesystem `path`; Azure returns a GUID + URL.** The host must either cache bytes locally or the contract must accept a URL in `path` (the `base.py` docstring already anticipates this).
3. **Auth.** PAT is deterministic; the Entra-token flow that `az boards` uses is identity-sensitive and failed on this machine's default login.

## What was tested

| Step | Method | Result |
|---|---|---|
| Create probe work item | `az boards work-item create --type "User Story"` | ✓ WI #20 |
| Upload attachment (69 B PNG) | extension SDK `create_attachment(upload_stream=...)` | ✓ id `031583d4…` |
| Upload attachment (724 KB PNG) | same | ✓ id `70c4ad47…` |
| Link to work item | `update_work_item` with `AttachedFile` relation patch | ✓ WI #20 rev 3 |
| List back | `get_work_item(id=20, expand="Relations")` | ✓ both, with `attributes.name` + `comment` |
| List back (CLI) | `az boards work-item show --expand relations` | ✓ name + `resourceSize`, no download verb |
| Download | SDK `get_attachment_content(id=…, download=True)` | ✓ 724174 B, SHA-256 identical to source |

## Why `az` alone does not work

- `az boards work-item` has no attachment subcommand. Feature request [Azure/azure-devops-cli-extension#1359](https://github.com/Azure/azure-devops-cli-extension/issues/1359) is open and unimplemented.
- `az devops invoke` unconditionally runs `json.loads(read_file_content(in_file, encoding='utf-8'))` before the request is built, so a binary or non-JSON `--in-file` fails at decode/parse time. `--media-type application/octet-stream` (or `image/png`) is accepted but only sets the outgoing header; it does not change how the file is read. Confirmed still true on `master` of the extension.
- Raw REST `POST /_apis/wit/attachments` with the token from `az account get-access-token --resource 499b84ac-1321-427f-aa17-267ca6975798` returned HTTP 302 to Entra sign-in, then HTTP 401 `TF400813` once `X-TFS-FedAuthRedirect: Suppress` was added. On this box the default `az` identity (`e3cb59e6-…`) is not a member of the org.

## Why the SDK path works

`az boards` succeeds because the azure-devops extension does not use the default-identity token directly.
`azext_devops.dev.common.services.get_connection(org)` loops over every cached `az login` tenant/identity, mints an Entra token per identity for resource `499b84ac-1321-427f-aa17-267ca6975798`, wraps it as `msrest.authentication.BasicAuthentication('', token)` (token as the Basic password, not a Bearer header), and uses the first one the org accepts. PAT via `AZURE_DEVOPS_EXT_PAT` or `az devops login` is the fallback.

The same SDK ships as the standalone `azure-devops` PyPI package (`from azure.devops.connection import Connection`); the calls are identical and only the credential construction differs.

## Round-trip code (as run)

```python
from azext_devops.dev.common.services import get_connection
conn = get_connection("https://dev.azure.com/madushan92")
client = conn.get_client(
    "azext_devops.devops_sdk.v5_0.work_item_tracking.work_item_tracking_client.WorkItemTrackingClient")

# upload
with open(src, "rb") as f:
    ref = client.create_attachment(upload_stream=f, file_name="shot.png", project="pdlc-scratch")

# link
client.update_work_item(id=20, document=[{
    "op": "add", "path": "/relations/-",
    "value": {"rel": "AttachedFile", "url": ref.url,
              "attributes": {"comment": "..."}}}])

# list back
wi = client.get_work_item(id=20, project="pdlc-scratch", expand="Relations")
atts = [(r.attributes.get("name"), r.url) for r in wi.relations if r.rel == "AttachedFile"]

# download
aid = ref.url.rstrip("/").split("/")[-1].split("?")[0]
stream = client.get_attachment_content(id=aid, project="pdlc-scratch",
                                       file_name="shot.png", download=True)
```

## Port mapping

| `AttachmentHost` concept | File host today | Azure DevOps |
|---|---|---|
| `scope` | work-item number, one dir under `.pdlc/` | work-item id — `AttachedFile` relations hang off exactly that |
| `save_for` return `id` | `att_<sha256>` | attachment GUID from `create_attachment` |
| `save_for` return `path` | local file path | **mismatch** — GUID + URL only; cache locally or return the URL |
| `description` | manifest field | `AttachedFile` relation `attributes.comment` ✓ |
| `list_for` | read `files.json` | read `AttachedFile` relations off the work item ✓ |
| `get_image_for` | local path, image check | download to cache dir, then image check |
| `capabilities` | `{"local_path"}` | `{"local_path"}` only if the host caches; else a new capability |

## If built

- New `src/pdlc/hosts/lib/azure/attachment_host.py` with `AzureAttachmentHost`, wired into `hosts/attachment_host/__init__.py` as `elif name == "azure"`.
- A connection helper — either add `azure-devops` to `pyproject.toml` and construct `Connection(base_url, BasicAuthentication('', pat))`, or reuse the vendored `azext_devops.devops_sdk` through `get_connection` (private API, matches the `az` shell-out precedent in `transport.py`).
- Decide `path` semantics: a local cache dir keyed by attachment GUID keeps `capabilities = {"local_path"}` and the inspectors unchanged; returning a URL is lighter but needs inspector support.
- Tests mirroring `tests/test_azure_hosts.py`, plus provider-contract coverage.
- Rough size: ~150 lines plus tests.

## Scratch board

Organization `https://dev.azure.com/madushan92`, project `pdlc-scratch`, team `pdlc-scratch Team`, work-item type `User Story`.
Work item #20 carries the two probe attachments (`pdlc-attach-test.png` 69 B, `pat-question-screenshot.png` 724 KB).
