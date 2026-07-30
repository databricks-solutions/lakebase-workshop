"""Load test routes: start/stop synthetic traffic, stream metrics via SSE.

Designed to trigger Lakebase autoscaling by pushing CPU, memory, and working set:
  - Writes: batch INSERT via generate_series with ~500-byte JSONB payloads
  - Reads: CPU-heavy queries (random sorts, md5 hashing, window functions, JSONB ops)
  - Connection pooling for realistic concurrent pressure
"""

import asyncio
import json
import random
import time
import uuid
from collections import deque
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .db import get_pooled_connection, get_pool, get_db_metrics
from .user_context import UserContext, get_current_user

router = APIRouter(prefix="/api/loadtest", tags=["loadtest"])

_active_tests: dict[str, dict] = {}

_READ_QUERIES_LIGHT = [
    (
        "SELECT event_id, event_type, source, created_at "
        "FROM events ORDER BY event_id DESC LIMIT 50",
        "recent_events",
    ),
    (
        "SELECT event_type, count(*) AS cnt "
        "FROM events GROUP BY event_type ORDER BY cnt DESC",
        "count_by_type",
    ),
    (
        "SELECT count(*) AS total, "
        "min(created_at) AS earliest, max(created_at) AS latest "
        "FROM events",
        "basic_stats",
    ),
    (
        "SELECT source, count(*) AS cnt "
        "FROM events GROUP BY source ORDER BY cnt DESC LIMIT 20",
        "count_by_source",
    ),
    (
        "SELECT date_trunc('minute', created_at) AS minute, count(*) AS cnt "
        "FROM events GROUP BY 1 ORDER BY 1 DESC LIMIT 60",
        "time_series_light",
    ),
]

_READ_QUERIES_HEAVY = [
    (
        "SELECT event_type, count(*) AS cnt, "
        "avg(length(payload::text)) AS avg_size, "
        "sum(length(payload::text)) AS total_payload_bytes "
        "FROM (SELECT * FROM events ORDER BY event_id DESC LIMIT 50000) sub "
        "GROUP BY event_type ORDER BY cnt DESC",
        "agg_by_type",
    ),
    (
        "SELECT source, event_type, count(*) AS cnt, "
        "avg(length(payload::text)) AS avg_payload "
        "FROM (SELECT * FROM events ORDER BY event_id DESC LIMIT 50000) sub "
        "GROUP BY source, event_type "
        "ORDER BY cnt DESC LIMIT 200",
        "agg_source_type",
    ),
    (
        "SELECT date_trunc('minute', created_at) AS minute, "
        "count(*) AS cnt, count(DISTINCT event_type) AS types, "
        "avg(length(payload::text)) AS avg_payload "
        "FROM events GROUP BY 1 ORDER BY 1 DESC LIMIT 200",
        "time_series",
    ),
    (
        "SELECT event_type, "
        "percentile_cont(0.5) WITHIN GROUP (ORDER BY event_id) AS median_id, "
        "percentile_cont(0.95) WITHIN GROUP (ORDER BY event_id) AS p95_id, "
        "count(*) AS cnt "
        "FROM (SELECT * FROM events ORDER BY event_id DESC LIMIT 50000) sub "
        "GROUP BY event_type",
        "percentile",
    ),
    (
        "SELECT count(*) AS total FROM ("
        "  SELECT e.event_id FROM events e "
        "  JOIN audit_log a ON a.record_id = e.event_id "
        "  AND a.table_name = 'events' "
        "  LIMIT 10000"
        ") sub",
        "cross_join",
    ),
    (
        "SELECT event_type, event_id, "
        "row_number() OVER (PARTITION BY event_type ORDER BY created_at DESC) AS rn, "
        "count(*) OVER (PARTITION BY event_type) AS type_cnt, "
        "lag(event_id, 1) OVER (ORDER BY event_id) AS prev_id "
        "FROM (SELECT * FROM events ORDER BY event_id DESC LIMIT 20000) sub "
        "ORDER BY event_id DESC LIMIT 5000",
        "window_funcs",
    ),
    (
        "SELECT md5(string_agg(payload::text, '' ORDER BY random())) AS hash_val, "
        "count(*) AS rows_hashed "
        "FROM (SELECT payload FROM events ORDER BY event_id DESC LIMIT 5000) sub",
        "random_sort_hash",
    ),
]


class LoadTestRequest(BaseModel):
    concurrency: int = Field(default=10, ge=1, le=100)
    duration_seconds: int = Field(default=60, ge=5, le=600)
    write_ratio: float = Field(default=0.3, ge=0.0, le=1.0)
    write_batch_size: int = Field(default=500, ge=1, le=10000)
    branch_id: str | None = None


class LoadTestStatus(BaseModel):
    test_id: str
    running: bool
    elapsed_seconds: float
    total_queries: int
    total_errors: int
    qps: float
    avg_latency_ms: float
    p95_latency_ms: float
    read_queries: int = 0
    write_queries: int = 0
    lookup_queries: int = 0
    read_avg_latency_ms: float = 0
    write_avg_latency_ms: float = 0
    lookup_avg_latency_ms: float = 0
    read_errors: int = 0
    write_errors: int = 0
    lookup_errors: int = 0
    rows_written: int = 0
    rows_read: int = 0
    concurrency: int = 0
    write_ratio: float = 0
    write_batch_size: int = 0
    db_active_connections: int = 0
    db_cache_hit_ratio: float = 0


def _run_read_query(user: UserContext, branch_id: str | None, query_idx: int):
    """Run a mix of light and heavy queries to simulate realistic traffic."""
    use_heavy = (query_idx % 10) < 3
    if use_heavy:
        sql, _ = _READ_QUERIES_HEAVY[query_idx % len(_READ_QUERIES_HEAVY)]
    else:
        sql, _ = _READ_QUERIES_LIGHT[query_idx % len(_READ_QUERIES_LIGHT)]
    rows_scanned = 0
    start = time.monotonic()
    try:
        with get_pooled_connection(user, branch_id) as conn:
            start = time.monotonic()
            with conn.cursor() as cur:
                cur.execute(sql)
                results = cur.fetchall()
                if results:
                    first = results[0]
                    rows_scanned = first.get("total", 0) or first.get("cnt", 0) or first.get("rows_hashed", 0) or len(results)
                    rows_scanned = max(rows_scanned, len(results))
            return (time.monotonic() - start) * 1000, None, rows_scanned
    except Exception as e:
        return (time.monotonic() - start) * 1000, str(e), 0


def _run_point_lookup(user: UserContext, branch_id: str | None, max_event_id: int):
    """Single-row PK lookup on the events table -- the core OLTP read pattern."""
    target_id = random.randint(1, max(max_event_id, 1))
    start = time.monotonic()
    try:
        with get_pooled_connection(user, branch_id) as conn:
            start = time.monotonic()
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT event_id, event_type, source, payload, created_at "
                    "FROM events WHERE event_id = %s",
                    (target_id,),
                )
                result = cur.fetchone()
            return (time.monotonic() - start) * 1000, None, 1 if result else 0
    except Exception as e:
        return (time.monotonic() - start) * 1000, str(e), 0


def _refresh_max_event_id(user: UserContext, branch_id: str | None) -> int:
    """Fetch the current max event_id for point lookup targeting."""
    try:
        with get_pooled_connection(user, branch_id) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT max(event_id) AS m FROM events")
                row = cur.fetchone()
                return (row or {}).get("m") or 1
    except Exception:
        return 1


def _run_write_query(user: UserContext, branch_id: str | None, batch_size: int):
    """Batch insert with ~500-byte JSONB payloads to push I/O and working set."""
    start = time.monotonic()
    try:
        with get_pooled_connection(user, branch_id) as conn:
            start = time.monotonic()
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO events (event_type, source, payload) "
                    "SELECT 'loadtest', 'lab-console', "
                    "jsonb_build_object("
                    "  'ts', extract(epoch from now()), "
                    "  'seq', gs, "
                    "  'batch_id', md5(random()::text), "
                    "  'data', repeat(md5(random()::text), 8), "
                    "  'tags', array_to_json(ARRAY["
                    "    md5(random()::text), md5(random()::text), md5(random()::text)"
                    "  ]), "
                    "  'metrics', jsonb_build_object("
                    "    'cpu', random() * 100, "
                    "    'mem', random() * 100, "
                    "    'disk', random() * 1000, "
                    "    'net_in', random() * 500, "
                    "    'net_out', random() * 500"
                    "  )"
                    ") "
                    "FROM generate_series(1, %s) AS gs",
                    (batch_size,),
                )
                rows = cur.rowcount
                conn.commit()
            return (time.monotonic() - start) * 1000, None, rows
    except Exception as e:
        return (time.monotonic() - start) * 1000, str(e), 0


async def _worker(test_id: str, role: str, user: UserContext, branch_id: str | None):
    """Single async worker. role is 'write', 'lookup', or 'scan'."""
    state = _active_tests.get(test_id)
    if not state:
        return
    loop = asyncio.get_event_loop()
    query_counter = random.randint(0, len(_READ_QUERIES_HEAVY) + len(_READ_QUERIES_LIGHT) - 1)
    batch_size = state.get("write_batch_size", 500)
    max_retries = 2
    lookup_counter = 0

    while state["running"]:
        error = None
        latency = 0
        rows = 0

        for attempt in range(max_retries + 1):
            if role == "write":
                latency, error, rows = await loop.run_in_executor(
                    None, _run_write_query, user, branch_id, batch_size
                )
            elif role == "lookup":
                max_eid = state.get("max_event_id", 1)
                latency, error, rows = await loop.run_in_executor(
                    None, _run_point_lookup, user, branch_id, max_eid
                )
                lookup_counter += 1
                if lookup_counter % 100 == 0:
                    new_max = await loop.run_in_executor(
                        None, _refresh_max_event_id, user, branch_id
                    )
                    state["max_event_id"] = max(state.get("max_event_id", 1), new_max)
            else:
                latency, error, rows = await loop.run_in_executor(
                    None, _run_read_query, user, branch_id, query_counter
                )

            if error is None or attempt == max_retries:
                break
            await asyncio.sleep(0.1 * (attempt + 1))

        state["total_queries"] += 1
        state["latencies"].append(latency)

        if role == "write":
            state["rows_written"] += rows
            state["write_queries"] += 1
            state["write_latencies"].append(latency)
            if error:
                state["write_errors"] += 1
        elif role == "lookup":
            state["rows_read"] += rows
            state["lookup_queries"] += 1
            state["lookup_latencies"].append(latency)
            if error:
                state["lookup_errors"] += 1
        else:
            query_counter += 1
            state["rows_read"] += rows
            state["read_queries"] += 1
            state["read_latencies"].append(latency)
            if error:
                state["read_errors"] += 1

        if error:
            state["total_errors"] += 1
        await asyncio.sleep(0)


async def _orchestrator(test_id: str, req: LoadTestRequest, user: UserContext):
    """Manage the load test lifecycle."""
    state = _active_tests[test_id]

    get_pool(user, req.branch_id, min_size=4, max_size=min(req.concurrency + 5, 60))

    loop = asyncio.get_event_loop()
    max_eid = await loop.run_in_executor(
        None, _refresh_max_event_id, user, req.branch_id
    )
    state["max_event_id"] = max_eid

    read_workers = req.concurrency - int(req.concurrency * req.write_ratio)
    lookup_workers = max(1, read_workers // 2)
    scan_workers = read_workers - lookup_workers

    tasks = []
    for i in range(req.concurrency):
        pct = i / req.concurrency
        if pct < req.write_ratio:
            role = "write"
        elif i < int(req.concurrency * req.write_ratio) + lookup_workers:
            role = "lookup"
        else:
            role = "scan"
        tasks.append(asyncio.create_task(_worker(test_id, role, user, req.branch_id)))

    await asyncio.sleep(req.duration_seconds)
    state["running"] = False

    for t in tasks:
        t.cancel()
        try:
            await t
        except asyncio.CancelledError:
            pass


def _build_status(test_id: str, state: dict) -> LoadTestStatus:
    elapsed = time.monotonic() - state["start_time"]
    latencies = list(state["latencies"])
    sorted_lat = sorted(latencies) if latencies else [0]

    read_lats = list(state["read_latencies"])
    write_lats = list(state["write_latencies"])
    lookup_lats = list(state["lookup_latencies"])

    db_metrics = state.get("_db_metrics_cache", {})

    return LoadTestStatus(
        test_id=test_id,
        running=state["running"],
        elapsed_seconds=round(elapsed, 1),
        total_queries=state["total_queries"],
        total_errors=state["total_errors"],
        qps=round(state["total_queries"] / max(elapsed, 0.1), 1),
        avg_latency_ms=round(sum(sorted_lat) / max(len(sorted_lat), 1), 2),
        p95_latency_ms=round(sorted_lat[int(len(sorted_lat) * 0.95)] if sorted_lat else 0, 2),
        read_queries=state["read_queries"],
        write_queries=state["write_queries"],
        lookup_queries=state["lookup_queries"],
        read_avg_latency_ms=round(sum(read_lats) / max(len(read_lats), 1), 2) if read_lats else 0,
        write_avg_latency_ms=round(sum(write_lats) / max(len(write_lats), 1), 2) if write_lats else 0,
        lookup_avg_latency_ms=round(sum(lookup_lats) / max(len(lookup_lats), 1), 2) if lookup_lats else 0,
        read_errors=state["read_errors"],
        write_errors=state["write_errors"],
        lookup_errors=state["lookup_errors"],
        rows_written=state["rows_written"],
        rows_read=state["rows_read"],
        concurrency=state["concurrency"],
        write_ratio=state["write_ratio"],
        write_batch_size=state.get("write_batch_size", 500),
        db_active_connections=db_metrics.get("active_connections", 0),
        db_cache_hit_ratio=db_metrics.get("cache_hit_ratio", 0),
    )


def _owned_test(test_id: str, user: UserContext) -> dict:
    """Return the test state only if it belongs to the calling user, else 404.

    Ownership is enforced so one participant cannot observe or stop another
    participant's load test in the shared workshop app.
    """
    state = _active_tests.get(test_id)
    if not state or state.get("owner") != user.email:
        raise HTTPException(404, "Test not found")
    return state


@router.post("/start", response_model=LoadTestStatus)
async def start_load_test(req: LoadTestRequest, user: UserContext = Depends(get_current_user)):
    """Start a new load test."""
    # Per-user limit: a participant may only have one running test at a time.
    # (Other participants' tests do not block this user.)
    if any(s["running"] for s in _active_tests.values() if s.get("owner") == user.email):
        raise HTTPException(409, "You already have a load test running")

    test_id = str(uuid.uuid4())[:8]
    _active_tests[test_id] = {
        "running": True,
        "start_time": time.monotonic(),
        "total_queries": 0,
        "total_errors": 0,
        "latencies": deque(maxlen=10000),
        "concurrency": req.concurrency,
        "write_ratio": req.write_ratio,
        "write_batch_size": req.write_batch_size,
        "read_queries": 0,
        "write_queries": 0,
        "lookup_queries": 0,
        "read_latencies": deque(maxlen=5000),
        "write_latencies": deque(maxlen=5000),
        "lookup_latencies": deque(maxlen=5000),
        "read_errors": 0,
        "write_errors": 0,
        "lookup_errors": 0,
        "rows_written": 0,
        "rows_read": 0,
        "max_event_id": 1,
        "_db_metrics_cache": {},
        "branch_id": req.branch_id,
        "user": user,
        "owner": user.email,
    }

    asyncio.create_task(_orchestrator(test_id, req, user))

    return LoadTestStatus(
        test_id=test_id,
        running=True,
        elapsed_seconds=0,
        total_queries=0,
        total_errors=0,
        qps=0,
        avg_latency_ms=0,
        p95_latency_ms=0,
        concurrency=req.concurrency,
        write_ratio=req.write_ratio,
        write_batch_size=req.write_batch_size,
    )


@router.post("/stop/{test_id}")
def stop_load_test(test_id: str, user: UserContext = Depends(get_current_user)):
    """Stop a running load test (owner only)."""
    state = _owned_test(test_id, user)
    state["running"] = False
    return {"status": "stopped", "test_id": test_id}


@router.get("/active", response_model=LoadTestStatus)
def get_active_load_test(user: UserContext = Depends(get_current_user)):
    """Return the calling user's currently running load test, if any."""
    for tid, state in _active_tests.items():
        if state["running"] and state.get("owner") == user.email:
            state["_db_metrics_cache"] = get_db_metrics(user, state.get("branch_id"))
            return _build_status(tid, state)
    raise HTTPException(404, "No active load test")


@router.get("/status/{test_id}", response_model=LoadTestStatus)
def get_load_test_status(test_id: str, user: UserContext = Depends(get_current_user)):
    """Get current status of a load test (owner only)."""
    state = _owned_test(test_id, user)
    state["_db_metrics_cache"] = get_db_metrics(user, state.get("branch_id"))
    return _build_status(test_id, state)


@router.get("/stream/{test_id}")
async def stream_metrics(test_id: str, user: UserContext = Depends(get_current_user)):
    """Server-Sent Events stream of load test metrics (owner only)."""
    state = _owned_test(test_id, user)

    async def event_generator():
        while state.get("running", False):
            data = _build_status(test_id, state).model_dump()
            yield f"data: {json.dumps(data)}\n\n"
            await asyncio.sleep(1)

        yield f"data: {json.dumps({'running': False, 'test_id': test_id})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
