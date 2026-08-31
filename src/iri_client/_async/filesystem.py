"""Filesystem resource abstraction.

The Superfacility storage API exposes *synchronous* list/stat/copy operations
against a storage system.  IRI instead runs every filesystem operation through
an asynchronous task queue: the request returns a ``TaskSubmitResponse``
immediately, and the result is fetched by polling ``GET /task/{task_id}`` until
the task reaches a terminal state.

This module mirrors that shape: each operation has a ``submit_*`` form that
returns the raw ``AsyncTask`` (for callers that want to poll or cancel it
themselves) and a blocking form that awaits the task and returns its result.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, PrivateAttr

from .._models import TaskSubmitResponse
from .tasks import AsyncTask


class AsyncFilesystem(BaseModel):
    """
    Models a filesystem resource and its file operations.
    """

    id: str
    name: Optional[str] = None

    _client: Any = PrivateAttr(default=None)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def __init__(self, id: str, name: Optional[str] = None, client: Any = None, **kwargs):
        super().__init__(id=id, name=name, **kwargs)
        self._client = client

    async def _submit(
        self,
        command: str,
        method: str = "GET",
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
    ) -> AsyncTask:
        url = f"filesystem/{command}/{self.id}"
        if method == "GET":
            r = await self._client.get(url, params=params or {})
        elif method == "POST":
            r = await self._client.post(
                url, params=params or {}, json=json, files=files
            )
        elif method == "PUT":
            r = await self._client.put(url, params=params or {}, json=json)
        elif method == "DELETE":
            r = await self._client.delete(url, params=params or {})
        else:
            raise ValueError(f"unsupported HTTP method: {method}")
        response = TaskSubmitResponse.model_validate(r.json())
        return AsyncTask(id=response.task_id, client=self._client)

    def _task_result(self, task: AsyncTask) -> Any:
        return task.result.get("output") if task.result is not None else None

    def _content_result(self, task: AsyncTask) -> str:
        """The ``content`` member of a view/head/tail task result.

        When a view range is past the end of the file the backend can return
        an empty status instead, so the result may be ``None``.
        """
        result = self._task_result(task)
        if result is None:
            return ""
        if isinstance(result, dict):
            return result.get("content") or ""
        return result

    def _checksum_result(self, task: AsyncTask) -> str:
        """The ``checksum`` member of a checksum task result."""
        result = self._task_result(task)
        if isinstance(result, dict):
            return result.get("checksum") or ""
        return result or ""

    # -- operations that only need a path ---------------------------------

    async def submit_list(
        self,
        path: str = ".",
        show_hidden: Optional[bool] = None,
        recursive: Optional[bool] = None,
    ) -> AsyncTask:
        """
        Submit a directory listing task for ``path`` without waiting for it.

        :param path: The directory to list
        :param show_hidden: Whether to include hidden entries
        :param recursive: Whether to recurse into subdirectories
        :return: The submitted task
        :rtype: AsyncTask
        """
        return await self._submit(
            "ls",
            params={
                "path": path,
                **({"showHidden": show_hidden} if show_hidden is not None else {}),
                **({"recursive": recursive} if recursive is not None else {}),
            },
        )

    async def list(self, path: str = ".", **kwargs) -> list[Dict[str, Any]]:
        """
        List the entries of ``path``.

        Each entry is a dict with the keys ``name``, ``type``,
        ``link_target``, ``user``, ``group``, ``permissions``,
        ``last_modified``, and ``size``.
        """
        task = await self.submit_list(path, **kwargs)
        await task.wait()
        return self._task_result(task) or []

    async def submit_stat(self, path: str) -> AsyncTask:
        """Submit a stat task for ``path`` without waiting for it."""
        return await self._submit("stat", params={"path": path})

    async def stat(self, path: str) -> Dict[str, Any]:
        """
        Get stat information for ``path``.

        :return: Dict with mode, ino, dev, nlink, uid, gid, size, atime,
                 ctime, and mtime.
        :rtype: Dict[str, Any]
        """
        task = await self.submit_stat(path)
        await task.wait()
        return self._task_result(task)

    async def submit_view(
        self,
        path: str,
        start_position: Optional[int] = None,
        end_position: Optional[int] = None,
    ) -> AsyncTask:
        """Submit a view task for ``path`` without waiting for it."""
        params: Dict[str, Any] = {"path": path}
        if start_position is not None:
            params["start_position"] = start_position
        if end_position is not None:
            params["end_position"] = end_position
        return await self._submit("view", params=params)

    async def view(
        self,
        path: str,
        start_position: Optional[int] = None,
        end_position: Optional[int] = None,
    ) -> str:
        """
        Return the contents of ``path`` as a string.

        :return: The file contents
        :rtype: str
        """
        task = await self.submit_view(path, start_position, end_position)
        await task.wait()
        return self._content_result(task)

    async def submit_head(
        self, path: str, lines: Optional[int] = None, bytes_: Optional[int] = None
    ) -> AsyncTask:
        """Submit a head task for ``path`` without waiting for it."""
        params: Dict[str, Any] = {"path": path}
        if lines is not None:
            params["lines"] = lines
        if bytes_ is not None:
            params["bytes"] = bytes_
        return await self._submit("head", params=params)

    async def head(self, path: str, **kwargs) -> str:
        """
        Read the first lines (or bytes) of ``path``.

        :return: The requested portion of the file contents
        :rtype: str
        """
        task = await self.submit_head(path, **kwargs)
        await task.wait()
        return self._content_result(task)

    async def submit_tail(
        self, path: str, lines: Optional[int] = None, bytes_: Optional[int] = None
    ) -> AsyncTask:
        """Submit a tail task for ``path`` without waiting for it."""
        params: Dict[str, Any] = {"path": path}
        if lines is not None:
            params["lines"] = lines
        if bytes_ is not None:
            params["bytes"] = bytes_
        return await self._submit("tail", params=params)

    async def tail(self, path: str, **kwargs) -> str:
        """
        Read the last lines (or bytes) of ``path``.

        :return: The requested portion of the file contents
        :rtype: str
        """
        task = await self.submit_tail(path, **kwargs)
        await task.wait()
        return self._content_result(task)

    async def submit_checksum(self, path: str) -> AsyncTask:
        """Submit a checksum task for ``path`` without waiting for it."""
        return await self._submit("checksum", params={"path": path})

    async def checksum(self, path: str) -> str:
        """
        Compute the SHA-256 checksum of ``path``.

        :return: The hexadecimal checksum
        :rtype: str
        """
        task = await self.submit_checksum(path)
        await task.wait()
        return self._checksum_result(task)

    # -- operations with a JSON body --------------------------------------

    async def submit_mkdir(self, path: str, parent: bool = False) -> AsyncTask:
        """Submit a mkdir task without waiting for it."""
        return await self._submit(
            "mkdir", method="POST", json={"path": path, "parent": parent}
        )

    async def mkdir(self, path: str, parent: bool = False) -> None:
        """
        Create the directory ``path``.

        :param parent: Whether to create intermediate directories as needed
        """
        task = await self.submit_mkdir(path, parent)
        await task.wait()

    async def submit_chmod(self, path: str, mode: str) -> AsyncTask:
        """Submit a chmod task without waiting for it."""
        return await self._submit(
            "chmod", method="PUT", json={"path": path, "mode": mode}
        )

    async def chmod(self, path: str, mode: str) -> None:
        """
        Change the permissions of ``path`` to ``mode`` (e.g. ``"750"``).
        """
        task = await self.submit_chmod(path, mode)
        await task.wait()

    async def submit_chown(
        self, path: str, user: Optional[str] = None, group: Optional[str] = None
    ) -> AsyncTask:
        """Submit a chown task without waiting for it."""
        payload: Dict[str, Any] = {"path": path}
        if user is not None:
            payload["user"] = user
        if group is not None:
            payload["group"] = group
        return await self._submit("chown", method="PUT", json=payload)

    async def chown(
        self, path: str, user: Optional[str] = None, group: Optional[str] = None
    ) -> None:
        """
        Change the owner and/or group of ``path``.
        """
        task = await self.submit_chown(path, user, group)
        await task.wait()

    async def submit_copy(self, path: str, target_path: str) -> AsyncTask:
        """Submit a copy task without waiting for it."""
        return await self._submit(
            "cp", method="POST", json={"path": path, "target_path": target_path}
        )

    async def copy(self, path: str, target_path: str) -> None:
        """Copy ``path`` to ``target_path``."""
        task = await self.submit_copy(path, target_path)
        await task.wait()

    async def submit_move(self, path: str, target_path: str) -> AsyncTask:
        """Submit a move task without waiting for it."""
        return await self._submit(
            "mv", method="POST", json={"path": path, "target_path": target_path}
        )

    async def move(self, path: str, target_path: str) -> None:
        """Move ``path`` to ``target_path``."""
        task = await self.submit_move(path, target_path)
        await task.wait()

    async def submit_symlink(self, path: str, link_path: str) -> AsyncTask:
        """Submit a symlink task without waiting for it."""
        return await self._submit(
            "symlink", method="POST", json={"path": path, "link_path": link_path}
        )

    async def symlink(self, path: str, link_path: str) -> None:
        """
        Create a symbolic link ``link_path`` pointing at ``path``.
        """
        task = await self.submit_symlink(path, link_path)
        await task.wait()

    async def submit_rm(self, path: str) -> AsyncTask:
        """Submit an rm task without waiting for it."""
        return await self._submit("rm", method="DELETE", params={"path": path})

    async def rm(self, path: str) -> None:
        """
        Remove ``path`` (file, directory, or symlink).
        """
        task = await self.submit_rm(path)
        await task.wait()

    async def submit_upload(
        self, local_path: str, remote_path: str, mode: Optional[str] = None
    ) -> AsyncTask:
        """Submit an upload task without waiting for it."""
        params = {"path": remote_path}
        if mode is not None:
            params["mode"] = mode
        return await self._submit(
            "upload",
            method="POST",
            params=params,
            files={"file": (local_path, open(local_path, "rb"))},
        )

    async def upload(self, local_path: str, remote_path: str) -> None:
        """
        Upload the small local file ``local_path`` to ``remote_path``.
        """
        task = await self.submit_upload(local_path, remote_path)
        await task.wait()

    async def submit_compress(
        self, path: str, target_path: str, compression: str = "gzip"
    ) -> AsyncTask:
        """Submit a compress task without waiting for it."""
        return await self._submit(
            "compress",
            method="POST",
            json={
                "path": path,
                "target_path": target_path,
                "compression": compression,
            },
        )

    async def compress(self, path: str, target_path: str, compression: str = "gzip") -> None:
        """Compress ``path`` into an archive at ``target_path``."""
        task = await self.submit_compress(path, target_path, compression)
        await task.wait()

    async def submit_extract(
        self, path: str, target_path: str, compression: str = "gzip"
    ) -> AsyncTask:
        """Submit an extract task without waiting for it."""
        return await self._submit(
            "extract",
            method="POST",
            json={
                "path": path,
                "target_path": target_path,
                "compression": compression,
            },
        )

    async def extract(self, path: str, target_path: str, compression: str = "gzip") -> None:
        """Extract the archive ``path`` into ``target_path``."""
        task = await self.submit_extract(path, target_path, compression)
        await task.wait()

    # -- convenience alias used downstream by paths.py --------------------

    async def submit_download(self, path: str) -> AsyncTask:
        """Submit a download task without waiting for it."""
        return await self._submit("download", params={"path": path})

    async def download(self, path: str) -> Any:
        """
        Download the contents of ``path``.
        """
        task = await self.submit_download(path)
        await task.wait()
        return self._task_result(task)