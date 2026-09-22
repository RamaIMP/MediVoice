"""Run API + agent together so they share the demo SQLite session database."""
import asyncio
import os
import signal
import sys


def commands(port):
    port = int(port)
    if not 1 <= port <= 65535 or port == 8081:
        raise ValueError("PORT must be 1–65535 and not the agent health port 8081")
    return [
        [sys.executable, "-m", "uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", str(port)],
        [sys.executable, "-m", "apps.voice_agent", "start"],
    ]


async def run():
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stopped.set)
    processes, watchers = [], []
    failed = False
    try:
        for command in commands(os.environ.get("PORT", "8080")):
            processes.append(await asyncio.create_subprocess_exec(*command, start_new_session=True))
        watchers = [asyncio.create_task(p.wait()) for p in processes]
        watchers.append(asyncio.create_task(stopped.wait()))
        done, _ = await asyncio.wait(watchers, return_when=asyncio.FIRST_COMPLETED)
        failed = any(task in done for task in watchers[:-1])
    finally:
        for process in processes:
            if process.returncode is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
        try:
            await asyncio.wait_for(asyncio.gather(*(p.wait() for p in processes)), timeout=30)
        except asyncio.TimeoutError:
            for process in processes:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            await asyncio.gather(*(p.wait() for p in processes))
        for task in watchers:
            task.cancel()
        await asyncio.gather(*watchers, return_exceptions=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
