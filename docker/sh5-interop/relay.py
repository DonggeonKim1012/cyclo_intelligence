"""Bridge explicitly selected Cyclo TCP ports to local Unix sockets.

Runs in Cyclo's existing isolated network namespace. Does not expose ROS
discovery, start robot nodes, or require host networking for the robot.
"""
import asyncio
import fcntl
import os
from pathlib import Path

ROOT = Path('/workspace/.web-relay')
PORTS = {7090: 17790, 7082: 17782, 7085: 17785, 7086: 17786, 7100: 17710}


async def bridge(reader, writer, port):
    upstream = None
    tasks = []
    try:
        remote_reader, upstream = await asyncio.wait_for(
            asyncio.open_connection('127.0.0.1', PORTS[port]), timeout=5)

        async def pump(source, target):
            while data := await source.read(65536):
                target.write(data)
                await target.drain()

        tasks = [asyncio.create_task(pump(reader, upstream)),
                 asyncio.create_task(pump(remote_reader, writer))]
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    except (OSError, asyncio.TimeoutError) as exc:
        print(f'Upstream {port}: {exc}', flush=True)
    finally:
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        writer.close()
        if upstream:
            upstream.close()


async def main():
    ROOT.mkdir(mode=0o755, exist_ok=True)
    with (ROOT / 'relay.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        servers = []
        for port in PORTS:
            path = ROOT / f'{port}.sock'
            if path.exists():
                if not path.is_socket():
                    raise RuntimeError(f'Not a socket: {path}')
                path.unlink()
            server = await asyncio.start_unix_server(
                lambda r, w, port=port: bridge(r, w, port), path=path)
            os.chmod(path, 0o666)
            servers.append(server)
        print(f'Unix relays ready: {PORTS}', flush=True)
        await asyncio.gather(*(server.serve_forever() for server in servers))


if __name__ == '__main__':
    asyncio.run(main())
