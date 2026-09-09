"""Resource checks shared by task owned heavy jobs."""

import contextlib
import fcntl
import os


def check_capacity(*, now, deadline, estimate_seconds, reserve_seconds,
                   free_bytes, min_free_bytes, used_bytes, max_bytes,
                   estimate_bytes):
    if now + estimate_seconds + reserve_seconds > deadline:
        raise RuntimeError("Job exceeds deadline with recovery reserve")
    if (free_bytes - estimate_bytes < min_free_bytes
            or used_bytes + estimate_bytes > max_bytes):
        raise RuntimeError("Job exceeds storage allowance or free space reserve")


@contextlib.contextmanager
def heavy_lock(path):
    # The kernel releases flock after a process exits, including abnormal exits.
    with open(path, "a+") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("Another heavy job holds the resource lock") from error
        try:
            handle.seek(0)
            handle.truncate()
            handle.write(str(os.getpid()))
            handle.flush()
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
