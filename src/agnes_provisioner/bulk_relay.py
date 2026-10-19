"""Metered copy of the proven existing-local-upstream -> provider relay."""

from __future__ import annotations

import asyncio
from urllib.parse import urlsplit


class MeteredRelay:
    def __init__(self, upstream, destination, meter):
        self.upstream, self.destination = urlsplit(upstream), urlsplit(destination)
        if (
            self.upstream.scheme != "http"
            or self.upstream.hostname not in ("127.0.0.1", "localhost", "::1")
            or self.upstream.username
            or self.upstream.password
            or not self.upstream.port
        ):
            raise ValueError("EXISTING_LOCAL_UPSTREAM_REQUIRED")
        if not self.destination.hostname or not self.destination.port:
            raise ValueError("PROXY_GATEWAY_INVALID")
        self.meter = meter
        self.sent_bytes = self.received_bytes = 0
        self.connections = set()

    async def __aenter__(self):
        self.server = await asyncio.start_server(self.handle, "127.0.0.1", 0)
        self.url = "http://127.0.0.1:" + str(self.server.sockets[0].getsockname()[1])
        return self

    async def __aexit__(self, *_):
        self.server.close()
        await self.server.wait_closed()
        pending = list(self.connections)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)

    async def pipe(self, reader, writer, outbound):
        while data := await reader.read(65536):
            if outbound:
                self.sent_bytes += len(data)
            else:
                self.received_bytes += len(data)
            # Persist each chunk, including transport setup/failures. A crash cannot reset usage.
            self.meter(self.sent_bytes, self.received_bytes)
            writer.write(data)
            await writer.drain()

    async def handle(self, reader, writer):
        task = asyncio.current_task()
        self.connections.add(task)
        remote_writer, children = None, []
        try:
            remote_reader, remote_writer = await asyncio.wait_for(
                asyncio.open_connection(self.upstream.hostname, self.upstream.port), 15
            )
            authority = f"{self.destination.hostname}:{self.destination.port}"
            remote_writer.write(
                f"CONNECT {authority} HTTP/1.1\r\nHost: {authority}\r\n\r\n".encode("ascii")
            )
            await remote_writer.drain()
            headers = await asyncio.wait_for(remote_reader.readuntil(b"\r\n\r\n"), 15)
            if int(headers.split(b"\r\n", 1)[0].split()[1]) != 200:
                writer.write(b"HTTP/1.1 502 Upstream unavailable\r\nContent-Length: 0\r\n\r\n")
                await writer.drain()
                return
            children = [
                asyncio.create_task(self.pipe(reader, remote_writer, True)),
                asyncio.create_task(self.pipe(remote_reader, writer, False)),
            ]
            await asyncio.wait(children, return_when=asyncio.FIRST_COMPLETED)
        except (
            OSError,
            ValueError,
            asyncio.TimeoutError,
            asyncio.IncompleteReadError,
            asyncio.LimitOverrunError,
        ):
            pass
        finally:
            for child in children:
                child.cancel()
            await asyncio.gather(*children, return_exceptions=True)
            if remote_writer:
                remote_writer.close()
            writer.close()
            self.connections.discard(task)
