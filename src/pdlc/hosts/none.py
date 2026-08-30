"""Public no-op host facade."""

from pdlc.hosts.code_host.none import NoneCodeHost
from pdlc.hosts.attachment_host.none import NoneAttachmentHost

__all__ = ["NoneAttachmentHost", "NoneCodeHost"]
