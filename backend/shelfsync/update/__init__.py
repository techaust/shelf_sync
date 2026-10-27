"""Signed in-app updates (SYS-06) and the database safety net around them (SYS-07).

The guarantee: ShelfSync installs no code whose manifest isn't signed by the owner's offline Ed25519 key, and every
file is checked against that manifest (06 section 6).
"""
