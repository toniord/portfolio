"""Message Batches for Stage 0, Stage B and Stage C. Added 2026-11-15.

The Batches API bills every token at half the price of the same call made one at
a time. The price of that is waiting: a batch is answered when Anthropic gets to
it, usually within minutes and at most 24 hours. Nothing in this system needs an
answer in seconds, so the trade is a good one.

How a run uses it:

    1. collect   every pending batch of this kind that has ended is read and its
                 answers are handed back. Free, and done first, so a batch
                 submitted by an earlier run is never wasted.
    2. submit    what is still owed a call goes out as one batch, minus anything
                 already in a pending batch, so a slow batch is never paid twice.
    3. wait      for a capped number of seconds. If it ends in time its answers
                 are handed back in the same run; if not, its id stays in
                 agent_state and the next run collects it (step 1).

A posting waiting on a batch keeps its empty tag or score, which is exactly the
state a capped run already left postings in, so everything downstream (NOT YET
SCORED in the digest, the pending count in the prefilter) already copes.

The pending list lives in agent_state under one key per kind, and is written the
moment a batch is created, before any waiting. A run killed by its step timeout
while waiting therefore loses nothing: the batch was paid for and recorded, and
the next run picks it up. That ordering is the same rule as the heartbeat in
CLAUDE.md rule 12: record first, then do the thing that can fail.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone

from . import db

# Anthropic keeps a batch for 24 hours before expiring whatever it has not
# answered, and keeps results for 29 days. Past this age a batch that has still
# not ended is dropped from the pending list so its postings are asked again.
STALE_AFTER = timedelta(hours=26)


def _key(kind: str) -> str:
    return f"pending_batches:{kind}"


def pending(conn, kind: str) -> list[dict]:
    """Batches of this kind submitted and not yet collected."""
    raw = db.get_state(conn, _key(kind))
    try:
        return json.loads(raw) if raw else []
    except ValueError:
        return []


def _save(conn, kind: str, entries: list[dict]) -> None:
    db.set_state(conn, _key(kind), json.dumps(entries))


def in_flight(conn, kind: str) -> set[str]:
    """custom_ids already submitted in a batch nobody has collected yet."""
    return {cid for entry in pending(conn, kind) for cid in entry["ids"]}


def submit(conn, client, kind: str, requests: list[dict], meta: dict | None = None) -> str:
    """Create a batch and record it as pending before returning its id.

    `requests` are `{"custom_id": ..., "params": {...}}` dicts, the shape the
    Batches API takes. `meta` is anything the collector will need that the
    answer itself does not carry, keyed by custom_id.
    """
    batch = client.messages.batches.create(requests=requests)
    entries = pending(conn, kind)
    entries.append({
        "id": batch.id,
        "submitted_at": db.now(),
        "ids": [r["custom_id"] for r in requests],
        "meta": meta or {},
    })
    _save(conn, kind, entries)
    return batch.id


def wait(client, batch_id: str, seconds: float, poll_every: float = 15.0,
         sleep=time.sleep, clock=time.monotonic) -> bool:
    """Poll until the batch ends or `seconds` pass. True if it ended."""
    deadline = clock() + max(0.0, seconds)
    while True:
        batch = client.messages.batches.retrieve(batch_id)
        if batch.processing_status == "ended":
            return True
        if clock() >= deadline:
            return False
        sleep(min(poll_every, max(0.0, deadline - clock())))


def _read(client, batch_id: str) -> dict[str, tuple[str, object]]:
    """custom_id -> ("succeeded", message) or (result type, error text)."""
    out: dict[str, tuple[str, object]] = {}
    for item in client.messages.batches.results(batch_id):
        kind = item.result.type
        if kind == "succeeded":
            out[item.custom_id] = ("succeeded", item.result.message)
        else:
            detail = getattr(getattr(item.result, "error", None), "type", "") or kind
            out[item.custom_id] = (kind, str(detail))
    return out


def _age(entry: dict) -> timedelta:
    try:
        then = datetime.fromisoformat(entry["submitted_at"])
    except (KeyError, ValueError):
        return timedelta(0)
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - then


def collect(conn, client, kind: str, only: str | None = None) -> list[tuple[dict, dict]]:
    """Read every ended batch of this kind and drop it from the pending list.

    Returns (entry, answers) pairs, where `answers` maps custom_id to the
    ("succeeded", message) or (error type, detail) tuple from `_read`. A batch
    still running stays pending. One that is past STALE_AFTER and still not
    ended is dropped, so its postings are owed a call again and get one.

    `only` restricts collection to one batch id, for the same-run wait path.
    A batch whose results cannot be read this time stays pending and is tried
    again next run; a read failure is never allowed to lose a paid answer.
    """
    collected: list[tuple[dict, dict]] = []
    keep: list[dict] = []
    for entry in pending(conn, kind):
        if only is not None and entry["id"] != only:
            keep.append(entry)
            continue
        try:
            status = client.messages.batches.retrieve(entry["id"]).processing_status
        except Exception:  # noqa: BLE001  network trouble: try again next run
            keep.append(entry)
            continue
        if status != "ended":
            if _age(entry) <= STALE_AFTER:
                keep.append(entry)
            continue
        try:
            answers = _read(client, entry["id"])
        except Exception:  # noqa: BLE001
            keep.append(entry)
            continue
        collected.append((entry, answers))
    _save(conn, kind, keep)
    return collected


def usage(message) -> dict:
    """Token counts off one answered message, in the shape the stages account in."""
    u = message.usage
    return {
        "input_tokens": u.input_tokens,
        "output_tokens": u.output_tokens,
        "cache_read_tokens": getattr(u, "cache_read_input_tokens", 0) or 0,
        "cache_write_tokens": getattr(u, "cache_creation_input_tokens", 0) or 0,
    }


def text(message) -> str:
    return next((b.text for b in message.content if b.type == "text"), "{}")
