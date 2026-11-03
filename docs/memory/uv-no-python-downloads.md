---
name: uv-no-python-downloads
description: "uv silently downloads a Python interpreter when requires-python doesn't match an installed one; always pass UV_PYTHON_DOWNLOADS=never"
metadata:
  node_type: memory
  type: feedback
  originSessionId: f4026695-dced-42b2-8f93-078aa020cc52
  modified: 2026-10-27T11:45:10.324Z
---

On 2026-10-27 a throwaway `uv lock` with `requires-python = "==3.14.*"` made uv download a Python 3.14.7 build without the owner's yes (it then failed to set up inside the Claude package, V36). The owner approved deleting it afterwards.

**Why:** rule 8: no package or tool is installed without the owner's yes, and uv's automatic Python download counts.

**How to apply:** run every uv command that might need a different interpreter with `UV_PYTHON_DOWNLOADS=never` (or `--no-python-downloads`). To check wheel availability for a new Python, ask PyPI's JSON API (`https://pypi.org/pypi/<name>/<version>/json`) instead of re-locking: `uv.lock` keeps only wheels matching the current `requires-python`. Related: [[claude-app-msix-virtualization]]
