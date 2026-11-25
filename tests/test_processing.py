"""Exercise real subprocess reuse, deadlines, failure and subsequent recovery."""

import os
import time

from django.test import SimpleTestCase

from generation.errors import GenerationError
from generation.process import ProcessingSession


def child_pid():
    """Return process identity without any external service access."""
    return os.getpid()


def slow_task():
    """Represent stalled native inference or an unresponsive network operation."""
    time.sleep(30)


def failed_task():
    """Represent a sensitive upstream exception that must not leave the child."""
    raise RuntimeError("private upstream diagnostics")


class ProcessingTests(SimpleTestCase):
    """Use real spawned interpreters rather than mocked process timing."""

    def setUp(self):
        """Own and clean up the process created by each test."""
        self.session = ProcessingSession()
        self.addCleanup(self.session.close)

    def test_process_reuse(self):
        """Repeated jobs share a child so Whisper can reuse its loaded weights."""
        first = self.session.execute(child_pid, (), 5)
        self.assertNotEqual(first, os.getpid())
        self.assertEqual(first, self.session.execute(child_pid, (), 5))

    def test_timeout_and_recovery(self):
        """A hung task is killed and the next request gets a fresh process."""
        first = self.session.execute(child_pid, (), 5)
        started = time.monotonic()
        with self.assertRaises(GenerationError):
            self.session.execute(slow_task, (), 0.1)
        self.assertLess(time.monotonic() - started, 10)
        self.assertIsNone(self.session.process)
        self.assertNotEqual(first, self.session.execute(child_pid, (), 5))

    def test_failure_is_sanitized(self):
        """Upstream error messages never propagate into parent-facing exceptions."""
        with self.assertRaises(GenerationError) as caught:
            self.session.execute(failed_task, (), 5)
        self.assertNotIn("private", str(caught.exception))
        self.assertIsNone(self.session.process)

    def test_parallel_request_rejected(self):
        """Do not queue concurrent inference behind an unlimited wait."""
        self.session.lock.acquire()
        try:
            with self.assertRaisesMessage(GenerationError, "already running"):
                self.session.execute(child_pid, (), 5)
        finally:
            self.session.lock.release()
