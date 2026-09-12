"""
Cross-process advisory locking for the scheduled sweeps
(docs/worker-scheduler-operations.md §3).

The sweeps are already safe to run twice — every guarantee lives in a database
constraint or a state check, not in a convention (see that document's §2). What
they are NOT is useful to run twice AT THE SAME TIME: two workers over one
backlog mostly race each other for rows and duplicate provider calls.

This module is the overlap guard, and only that. It is deliberately NOT a
correctness mechanism: a skipped run is ordinary output, never an error,
because nothing is wrong when one happens.

Why a Postgres advisory lock rather than a row in a table or an in-process
flag:

  - It works across processes, containers and hosts. An in-memory lock would
    quietly fail exactly where this matters — two worker containers, which is
    the normal way to scale a worker.
  - It is released automatically when the connection drops, so a worker killed
    mid-sweep cannot wedge the job. A lock row in a table would need its own
    staleness/expiry logic, which is a second thing to get wrong.
  - It needs no migration and no new model. This project already requires
    Postgres (docs/project-master-spec.md), so this is an existing primitive,
    not a new dependency.

SESSION-level (`pg_try_advisory_lock`), not transaction-level
(`pg_try_advisory_xact_lock`): a sweep is many small transactions, one per row,
so there is no single enclosing transaction for the lock to live in — and
creating one would change the sweeps' commit semantics, which is a real
behaviour change made for the convenience of a lock.
"""

import contextlib
import hashlib
import logging

from django.db import connection

logger = logging.getLogger(__name__)

# Namespace for every lock this module takes. `pg_try_advisory_lock` with two
# int4 arguments partitions the advisory-lock space, so a key derived from a
# job name here can never collide with a key some other library derives its
# own way.
LOCK_NAMESPACE = 0x54454E4F  # "TENO"


def lock_key(name: str) -> int:
    """
    A stable int4 key for a job name. Derived from a hash (not `hash()`, which
    is salted per process and would give a different key on every restart —
    the one property a lock key must not have).
    """
    digest = hashlib.sha256(name.encode()).digest()
    # Signed 32-bit, because that is what pg_try_advisory_lock's second
    # argument is.
    return int.from_bytes(digest[:4], "big", signed=True)


@contextlib.contextmanager
def advisory_lock(name: str):
    """
    Try to take the advisory lock for `name`. Yields True if this process got
    it, False if another process already holds it.

    The caller decides what a False means — for the scheduled sweeps it means
    "another run is already doing this, return a skipped result". The lock is
    released in a `finally`, and only when it was actually acquired: releasing
    a lock this session does not hold would log a Postgres warning and, worse,
    could decrement a count another part of the session was relying on.

    Usage:

        with advisory_lock("billing.meter_usage") as acquired:
            if not acquired:
                return SKIPPED
            ...
    """
    key = lock_key(name)
    acquired = False
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_try_advisory_lock(%s, %s)", [LOCK_NAMESPACE, key]
            )
            acquired = bool(cursor.fetchone()[0])
        if not acquired:
            logger.info("advisory lock busy — skipping run of %s", name)
        yield acquired
    finally:
        if acquired:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_advisory_unlock(%s, %s)", [LOCK_NAMESPACE, key]
                )
