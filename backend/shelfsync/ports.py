"""The port numbers ShelfSync uses (SET-06). One place, so the setting default and the server agree."""

DEFAULT_PORT = 47615
LAST_PORT = 47624  # 47615-47624: ten ports in all
MIN_PORT = 1024  # below this are the system's ports
MAX_PORT = 65535
