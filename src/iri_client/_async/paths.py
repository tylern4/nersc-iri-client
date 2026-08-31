"""Path abstraction over a filesystem resource.

The Superfacility storage API exposes path helpers such as ``client.storage.get``
which mirror POSIX commands.  IRI exposes the same operations router by router
(``filesystem``), so this module provides an equivalent ``AsyncPath`` API on top
of ``AsyncFilesystem``.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from .filesystem import AsyncFilesystem


class AsyncPath:
    """
    Represents a path on an IRI filesystem resource.
    """

    def __init__(self, path: str, filesystem: AsyncFilesystem):
        """
        :param path: The remote path, relative to the resource root
        :param filesystem: The filesystem resource the path is on
        """
        self.path = path
        self._filesystem = filesystem

    async def list(self) -> list[Dict[str, Any]]:
        """
        List the entries in the directory at ``self.path``.
        """
        return await self._filesystem.list(self.path)

    async def ls(self) -> list[Dict[str, Any]]:
        """Deprecated alias of :meth:`list`."""
        return await self.list()

    async def stat(self) -> Dict[str, Any]:
        """
        Stat the path, returning mode, ino, dev, nlink, uid, gid, size, atime,
        ctime, and mtime.
        """
        return await self._filesystem.stat(self.path)

    async def view(self, start_position: Optional[int] = None, end_position: Optional[int] = None) -> str:
        """
        Return the contents of ``self.path`` as a string.
        """
        return await self._filesystem.view(self.path, start_position, end_position)

    async def head(self, lines: Optional[int] = None, bytes_: Optional[int] = None) -> str:
        """
        Read the first lines (or bytes) of ``self.path``.
        """
        return await self._filesystem.head(self.path, lines=lines, bytes_=bytes_)

    async def tail(self, lines: Optional[int] = None, bytes_: Optional[int] = None) -> str:
        """
        Read the last lines (or bytes) of ``self.path``.
        """
        return await self._filesystem.tail(self.path, lines=lines, bytes_=bytes_)

    async def checksum(self) -> str:
        """
        Compute the SHA-256 checksum of ``self.path``.
        """
        return await self._filesystem.checksum(self.path)

    async def download(self) -> bytes:
        """
        Download the contents of ``self.path``.
        """
        return await self._filesystem.download(self.path)

    async def upload(self, local_path: str) -> None:
        """
        Upload the local file ``local_path`` to ``self.path``.
        """
        await self._filesystem.upload(local_path, self.path)

    async def mkdir(self, parent: bool = False) -> None:
        """
        Create the directory at ``self.path``.
        """
        await self._filesystem.mkdir(self.path, parent=parent)

    async def touch(self) -> None:
        """
        Create ``self.path`` as an empty file.
        """
        import tempfile

        empty = tempfile.NamedTemporaryFile(delete=False)
        empty.close()
        try:
            await self.upload(empty.name)
        finally:
            os.unlink(empty.name)

    async def chmod(self, mode: str) -> None:
        """
        Change the permissions of ``self.path`` (e.g. ``"750"``).
        """
        await self._filesystem.chmod(self.path, mode)

    async def chown(self, user: Optional[str] = None, group: Optional[str] = None) -> None:
        """
        Change the owner and/or group of ``self.path``.
        """
        await self._filesystem.chown(self.path, user=user, group=group)

    async def copy(self, dest: "AsyncPath") -> None:
        """
        Copy ``self.path`` to the destination path.
        """
        await self._filesystem.copy(self.path, dest.path)

    async def move(self, dest: "AsyncPath") -> None:
        """
        Move ``self.path`` to the destination path.
        """
        await self._filesystem.move(self.path, dest.path)

    async def symlink(self, link_path: "AsyncPath") -> None:
        """
        Create ``link_path`` as a symbolic link pointing at ``self.path``.
        """
        await self._filesystem.symlink(self.path, link_path.path)

    async def rm(self) -> None:
        """
        Remove ``self.path``.
        """
        await self._filesystem.rm(self.path)

    async def compress(self, target_path: str, compression: str = "gzip") -> None:
        """
        Compress ``self.path`` into an archive target.
        """
        await self._filesystem.compress(self.path, target_path, compression)

    async def extract(self, target_path: str, compression: str = "gzip") -> None:
        """
        Extract the archive at ``self.path`` into ``target_path``.
        """
        await self._filesystem.extract(self.path, target_path, compression)

    @property
    def name(self) -> str:
        """The final component of the path."""
        return os.path.basename(self.path)

    @property
    def parent(self) -> "AsyncPath":
        """The parent directory of the path."""
        return AsyncPath(os.path.dirname(self.path), self._filesystem)

    def join(self, *components: str) -> "AsyncPath":
        """
        Join ``components`` onto ``self.path``.
        """
        return AsyncPath(os.path.join(self.path, *components), self._filesystem)

    def __str__(self) -> str:
        return self.path

    def __repr__(self) -> str:
        return f"AsyncPath({self.path!r})"

    def __truediv__(self, other: str) -> "AsyncPath":
        return self.join(other)