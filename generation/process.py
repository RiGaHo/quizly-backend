"""Synchronous reusable local subprocess with a hard deadline and group cleanup."""

import atexit
import multiprocessing
import os
import signal
from threading import Lock

from .errors import GenerationError


def child_loop(connection):
    """Run trusted local callables serially, retaining the loaded Whisper model."""
    os.setsid()
    connection.send("ready")
    try:
        while True:
            function, arguments = connection.recv()
            try:
                connection.send((True, function(*arguments)))
            except Exception:
                connection.send((False, "Generation processing failed."))
    except (EOFError, BrokenPipeError):
        connection.close()


class ProcessingSession:
    """Own one lazy child; this is an internal process, not a separate service."""

    def __init__(self):
        """Delay process creation until a generation is actually requested."""
        self.process = None
        self.connection = None
        self.lock = Lock()
        atexit.register(self.close)

    def start(self):
        """Spawn a clean interpreter and wait until its process group is ready."""
        context = multiprocessing.get_context("spawn")
        self.connection, child = context.Pipe()
        self.process = context.Process(target=child_loop, args=(child,), daemon=True)
        self.process.start()
        child.close()
        if not self.connection.poll(10) or self.connection.recv() != "ready":
            self.close()
            raise GenerationError("Processing initialization failed.")

    def execute(self, function, arguments, timeout):
        """Reject overlapping work and bound a synchronous job's entire execution."""
        if not self.lock.acquire(blocking=False):
            raise GenerationError("A generation is already running.")
        try:
            return self.exchange(function, arguments, timeout)
        except (EOFError, OSError, GenerationError) as error:
            self.close()
            raise GenerationError(
                "Generation failed or exceeded its deadline."
            ) from error
        finally:
            self.lock.release()

    def exchange(self, function, arguments, timeout):
        """Reuse the model-owning process and stop on an unresponsive task."""
        if self.process is None or not self.process.is_alive():
            self.close()
            self.start()
        self.connection.send((function, arguments))
        if not self.connection.poll(timeout):
            raise GenerationError("Processing deadline exceeded.")
        success, result = self.connection.recv()
        if not success:
            raise GenerationError("Generation processing failed.")
        return result

    def close(self):
        """Kill the child process group, including FFmpeg/Node descendants."""
        if self.process is not None:
            stop_process(self.process)
            self.process = None
        if self.connection is not None:
            self.connection.close()
            self.connection = None


def stop_process(process):
    """Terminate our own process group and reap the multiprocessing child."""
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        if process.is_alive():
            process.kill()
    process.join(timeout=5)
    if process.is_alive():
        process.kill()
        process.join()
    process.close()
