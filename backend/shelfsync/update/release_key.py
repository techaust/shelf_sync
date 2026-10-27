"""The release public key (06 section 6): the only key an update is checked against.

`PUBLIC_KEY` is the owner's Ed25519 public key as 32 raw bytes. It is None until the owner's key exists, and with
None every install and roll back is refused (the checks still run). Verification reads this constant and nothing
else: no setting, environment variable, file or API can replace it, so it changes only with a new release (06 section
6, runbook `key-rotation.md`). Tests patch the module attribute.
"""

PUBLIC_KEY: bytes | None = None
