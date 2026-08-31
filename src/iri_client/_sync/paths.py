"""Path abstraction over a filesystem resource.

The Superfacility storage API exposes path helpers such as ``client.storage.get``
which mirror POSIX commands.  IRI exposes the same operations router by router
(``filesystem``), so this module provides an equivalent ``Path`` API on top
of ``Filesystem``.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from .filesystem import Filesystem


class RemotePath:
    """
    Represents a path on an IRI filesystem resource.
    """

    def __init__(self, path: str, filesystem: Filesystem):
        """
        :param path: The remote path, relative to the resource root
        :param filesystem: The filesystem resource the path is on
        """
        self.path = path
        self._filesystem = filesystem

    def list(self) -> list[Dict[str, Any]]:
        """
        List the entries in the directory at ``self.path``.
        """
        return self._filesystem.list(self.path)

    def ls(self) -> list[Dict[str, Any]]:
        """Deprecated alias of :meth:`list`."""
        return self.list()

    def stat(self) -> Dict[str, Any]:
        """
        Stat the path, returning mode, ino, dev, nlink, uid, gid, size, atime,
        ctime, and mtime.
        """
        return self._filesystem.stat(self.path)

    def view(self, start_position: Optional[int] = None, end_position: Optional[int] = None) -> str:
        """
        Return the contents of ``self.path`` as a string.
        """
        return self._filesystem.view(self.path, start_position, end_position)

    def head(self, lines: Optional[int] = None, bytes_: Optional[int] = None) -> str:
        """
        Read the first lines (or bytes) of ``self.path``.
        """
        return self._filesystem.head(self.path, lines=lines, bytes_=bytes_)

    def tail(self, lines: Optional[int] = None, bytes_: Optional[int] = None) -> str:
        """
        Read the last lines (or bytes) of ``self.path``.
        """
        return self._filesystem.tail(self.path, lines=lines, bytes_=bytes_)

    def checksum(self) -> str:
        """
        Compute the SHA-256 checksum of ``self.path``.
        """
        return self._filesystem.checksum(self.path)

    def download(self) -> bytes:
        """
        Download the contents of ``self.path``.
        """
        return self._filesystem.download(self.path)

    def upload(self, local_path: str) -> None:
        """
        Upload the local file ``local_path`` to ``self.path``.
        """
        self._filesystem.upload(local_path, self.path)

    def mkdir(self, parent: bool = False) -> None:
        """
        Create the directory at ``self.path``.
        """
        self._filesystem.mkdir(self.path, parent=parent)

    def touch(self) -> None:
        """
        Create ``self.path`` as an empty file.
        """
        import tempfile

        empty = tempfile.NamedTemporaryFile(delete=False)
        empty.close()
        try:
            self.upload(empty.name)
        finally:
            os.unlink(empty.name)

    def chmod(self, mode: str) -> None:
        """
        Change the permissions of ``self.path`` (e.g. ``"750"``).
        """
        self._filesystem.chmod(self.path, mode)

    def chown(self, user: Optional[str] = None, group: Optional[str] = None) -> None:
        """
        Change the owner and/or group of ``self.path``.
        """
        self._filesystem.chown(self.path, user=user, group=group)

    def copy(self, dest: "RemotePath") -> None:
        """
        Copy ``self.path`` to the destination path.
        """
        self._filesystem.copy(self.path, dest.path)

    def move(self, dest: "RemotePath") -> None:
        """
        Move ``self.path`` to the destination path.
        """
        self._filesystem.move(self.path, dest.path)

    def symlink(self, link_path: "RemotePath") -> None:
        """
        Create ``link_path`` as a symbolic link pointing at ``self.path``.
        """
        self._filesystem.symlink(self.path, link_path.path)

    def rm(self) -> None:
        """
        Remove ``self.path``.
        """
        self._filesystem.rm(self.path)

    def compress(self, target_path: str, compression: str = "gzip") -> None:
        """
        Compress ``self.path`` into an archive target.
        """
        self._filesystem.compress(self.path, target_path, compression)

    def extract(self, target_path: str, compression: str = "gzip") -> None:
        """
        Extract the archive at ``self.path`` into ``target_path``.
        """
        self._filesystem.extract(self.path, target_path, compression)

    @property
    def name(self) -> str:
        """The final component of the path."""
        return os.path.basename(self.path)

    @property
    def parent(self) -> "RemotePath":
        """The parent directory of the path."""
        return RemotePath(os.path.dirname(self.path), self._filesystem)

    def join(self, *components: str) -> "RemotePath":
        """
        Join ``components`` onto ``self.path``.
        """
        return RemotePath(os.path.join(self.path, *components), self._filesystem)

    def __str__(self) -> str:
        return self.path

    def __repr__(self) -> str:
        return f"AsyncPath({self.path!r})"

    def __truediv__(self, other: str) -> "RemotePath":
        return self.join(other)