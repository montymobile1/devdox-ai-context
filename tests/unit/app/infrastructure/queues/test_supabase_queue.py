import json
from datetime import datetime, timedelta, timezone
import pytest

from app.infrastructure.queues.supabase_queue import SupabaseQueue

pytestmark = [pytest.mark.asyncio]

# --------- Fakes / Stubs ---------

class FakeMessage:
    def __init__(self, msg_id: int, message: dict):
        self.msg_id = msg_id
        self.message = message

class FakeMetrics:
    def __init__(self, queued=0, total=0, newest=0, oldest=0):
        self.queue_length = queued
        self.total_messages = total
        self.newest_msg_age_sec = newest
        self.oldest_msg_age_sec = oldest

class FakePGMQueue:
    def __init__(self):
        self.initted = 0
        self.closed = 0
        self.sent = []          # (queue, message, delay_used, via)
        self.deleted = []       # (queue, msg_id)
        self.archived = []      # (queue, msg_id)
        self.read_calls = []    # (queue, vt, batch_size)
        self._read_return = []
        self._send_should_raise = None
        self._delete_return = True
        self._archive_return = True
        self._metrics = FakeMetrics()

    # API used by SUT
    async def init(self):
        self.initted += 1

    async def close(self):
        self.closed += 1

    async def send(self, queue, message, delay=0, **kwargs):
        if self._send_should_raise:
            raise self._send_should_raise
        self.sent.append((queue, message, delay, "send"))
        # emulate PGMQ int ID
        return len(self.sent)

    async def send_delay(self, queue, message, delay):
        self.sent.append((queue, message, delay, "send_delay"))
        return len(self.sent)

    async def read_batch(self, queue, vt, batch_size):
        self.read_calls.append((queue, vt, batch_size))
        return self._read_return

    async def delete(self, queue, msg_id):
        self.deleted.append((queue, msg_id))
        return self._delete_return

    async def archive(self, queue, msg_id):
        self.archived.append((queue, msg_id))
        return self._archive_return

    async def metrics(self, queue):
        return self._metrics

# Simple fakes to capture calls from SupabaseQueue
class FakeJobTracker:
    def __init__(self, fail_on=None):
        self.completed_calls = 0
        self.retry_calls = []
        self.fail_calls = []
        self._fail_on = fail_on or set()  # {"completed", "retry", "fail"}

    async def completed(self):
        self.completed_calls += 1
        if "completed" in self._fail_on:
            raise RuntimeError("boom-completed")

    async def retry(self, message_id: str):
        self.retry_calls.append(message_id)
        if "retry" in self._fail_on:
            raise RuntimeError("boom-retry")

    async def fail(self, message_id: str):
        self.fail_calls.append(message_id)
        if "fail" in self._fail_on:
            raise RuntimeError("boom-fail")

class FakeJobTracer:
    def __init__(self):
        self.errors = []

    def record_error(self, *, summary: str, exc: BaseException = None):
        self.errors.append({"summary": summary, "exc": exc})

# --------- Fixtures ---------

@pytest.fixture
def fake_queue():
    return FakePGMQueue()

@pytest.fixture
def sut(fake_queue):
    q = SupabaseQueue(host="h", port="p", user="u", password="pw", db_name="db", table_name="tbl")
    # swap real PGMQueue for our fake (explicit DI would be nicer, but this keeps it pure unit)
    q.queue = fake_queue
    return q

# --------- _ensure_initialized ---------

async def test_ensure_initialized_calls_init_once(sut, fake_queue):
    await sut._ensure_initialized()
    await sut._ensure_initialized()
    assert fake_queue.initted == 1
    assert sut._initialized is True

async def test_ensure_initialized_bubbles_up_error(sut, fake_queue):
    async def boom():
        raise RuntimeError("init-fail")
    fake_queue.init = boom  # patch method on fake
    sut._initialized = False
    with pytest.raises(RuntimeError):
        await sut._ensure_initialized()
    assert sut._initialized is False

# --------- enqueue ---------

async def test_enqueue_without_delay_uses_send_and_serializes_payload_and_config(sut, fake_queue):
    payload = {"a": 1}
    job_id = await sut.enqueue("qA", payload, priority=7, job_type="jt", user_id="u1", config={"x": 2})
    assert job_id == "1"
    assert len(fake_queue.sent) == 1
    queue, msg, delay, via = fake_queue.sent[0]
    assert queue == "qA"
    assert via == "send"
    # payload & config serialized
    assert isinstance(msg["payload"], str) and json.loads(msg["payload"]) == payload
    assert isinstance(msg["config"], str) and json.loads(msg["config"]) == {"x": 2}
    assert msg["attempts"] == 0
    assert msg["priority"] == 7
    assert msg["status"] == "queued"
    assert msg["user_id"] == "u1"
    # scheduled_at is ISO and ~now
    datetime.fromisoformat(msg["scheduled_at"].replace("Z", "+00:00"))

async def test_enqueue_with_delay_uses_send_delay_and_future_schedule(sut, fake_queue):
    now = datetime.now(timezone.utc)
    job_id = await sut.enqueue("qB", {"k": "v"}, delay_seconds=30)
    assert job_id == "1"
    _, msg, delay, via = fake_queue.sent[0]
    assert via == "send_delay"
    assert delay == 30
    scheduled = datetime.fromisoformat(msg["scheduled_at"].replace("Z", "+00:00"))
    assert scheduled >= now + timedelta(seconds=29)

async def test_enqueue_logs_and_raises_on_send_error(sut, fake_queue, caplog):
    fake_queue._send_should_raise = RuntimeError("send-broke")
    with pytest.raises(RuntimeError):
        await sut.enqueue("qC", {"x": 1})
    assert any("Failed to enqueue job" in r.message for r in caplog.records)

# --------- _parse_json_field ---------

def test_parse_json_field_roundtrip_for_str_and_non_str(sut):
    assert sut._parse_json_field({"a": 1}) == {"a": 1}  # non-str passes through
    assert sut._parse_json_field('{"a":1}') == {"a": 1}
    # invalid JSON returns original
    assert sut._parse_json_field("{oops}") == "{oops}"

# --------- _is_job_type_allowed ---------

def test_is_job_type_allowed_matches_and_defaults(sut):
    assert sut._is_job_type_allowed({"job_type": "A"}, []) is True
    assert sut._is_job_type_allowed({"job_type": "A"}, ["A", "B"]) is True
    assert sut._is_job_type_allowed({"job_type": "C"}, ["A", "B"]) is False

# --------- _is_job_ready_for_processing ---------

def test_is_job_ready_for_processing_handles_missing_and_bad_format(sut, caplog):
    assert sut._is_job_ready_for_processing({}) is True
    assert sut._is_job_ready_for_processing({"scheduled_at": "not-a-date"}) is True
    assert any("Invalid scheduled_at format" in r.message for r in caplog.records)

def test_is_job_ready_for_processing_future_and_past(sut):
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    assert sut._is_job_ready_for_processing({"scheduled_at": future}) is False
    assert sut._is_job_ready_for_processing({"scheduled_at": past}) is True

# --------- _handle_max_attempts_exceeded ---------

async def test_handle_max_attempts_exceeded_archives_when_attempts_ge_max(sut, fake_queue):
    archived = await sut._handle_max_attempts_exceeded({"attempts": 3, "max_attempts": 3}, 42, "q")
    assert archived is True
    assert fake_queue.archived == [("q", 42)]

async def test_handle_max_attempts_exceeded_no_archive_if_under_max(sut, fake_queue):
    archived = await sut._handle_max_attempts_exceeded({"attempts": 1, "max_attempts": 3}, 42, "q")
    assert archived is False
    assert fake_queue.archived == []

# --------- _construct_job_data ---------

def test_construct_job_data_builds_expected_fields_and_increments_attempts(sut):
    msg = FakeMessage(7, {})
    message_data = {
        "job_type": "JT",
        "payload": '{"a":1}',
        "config": '{"b":2}',
        "priority": 5,
        "attempts": 2,
        "max_attempts": 9,
        "user_id": "U",
        "scheduled_at": datetime.now(timezone.utc).isoformat(),
    }
    jd = sut._construct_job_data(msg, message_data, "Q", "WID")
    assert jd["id"] == "7" and jd["pgmq_msg_id"] == 7
    assert jd["job_type"] == "JT"
    assert jd["payload"] == {"a": 1}
    assert jd["config"] == {"b": 2}
    assert jd["priority"] == 5
    assert jd["attempts"] == 3  # incremented
    assert jd["max_attempts"] == 9
    assert jd["user_id"] == "U"
    assert jd["queue_name"] == "Q"
    # started_at is ISO
    datetime.fromisoformat(jd["started_at"].replace("Z", "+00:00"))

# --------- _process_single_message ---------

async def test_process_single_message_filters_job_type(sut):
    m = FakeMessage(1, {"job_type": "NOPE"})
    assert await sut._process_single_message(m, "q", ["YES"], "w") is None

async def test_process_single_message_archives_when_over_max(sut, fake_queue):
    m = FakeMessage(1, {"job_type": "A", "attempts": 3, "max_attempts": 3})
    assert await sut._process_single_message(m, "q", ["A"], "w") is None
    assert fake_queue.archived == [("q", 1)]

async def test_process_single_message_skips_if_not_ready_yet(sut):
    fut = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    m = FakeMessage(1, {"job_type": "A", "scheduled_at": fut})
    assert await sut._process_single_message(m, "q", ["A"], "w") is None

async def test_process_single_message_returns_job_data_when_valid(sut):
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    m = FakeMessage(5, {"job_type": "A", "scheduled_at": past, "attempts": 0, "payload": '{"x":1}', "config": "{}"})
    jd = await sut._process_single_message(m, "q", ["A"], "workerX")
    assert jd and jd["id"] == "5" and jd["worker_id"] == "workerX"

# --------- _process_messages ---------

async def test_process_messages_returns_first_valid_and_continues_on_errors(sut, monkeypatch):
    msgs = [FakeMessage(1, {}), FakeMessage(2, {})]

    async def side_effect(message, *a, **kw):
        if message.msg_id == 1:
            raise RuntimeError("bad")
        return {"id": "2"}

    monkeypatch.setattr(sut, "_process_single_message", side_effect)
    got = await sut._process_messages(msgs, "q", [], "w")
    assert got == {"id": "2"}

async def test_process_messages_returns_none_if_no_valid(sut, monkeypatch):
    msgs = [FakeMessage(1, {}), FakeMessage(2, {})]
    async def always_none(*a, **k): return None
    monkeypatch.setattr(sut, "_process_single_message", always_none)
    assert await sut._process_messages(msgs, "q", [], "w") is None

# --------- dequeue ---------

async def test_dequeue_returns_none_on_empty_batch_and_uses_effective_queue(sut, fake_queue):
    fake_queue._read_return = []
    out = await sut.dequeue(visibility_timeout=17, batch_size=3)  # queue_name=None -> table_name
    assert out is None
    assert fake_queue.read_calls == [("tbl", 17, 3)]

async def test_dequeue_returns_processed_job(sut, fake_queue, monkeypatch):
    fake_queue._read_return = [FakeMessage(9, {"job_type": "A"})]
    async def proc(*a, **k): return {"id": "9"}
    monkeypatch.setattr(sut, "_process_messages", proc)
    out = await sut.dequeue(queue_name="WorkQ", job_types=["A"], worker_id="W", batch_size=2, visibility_timeout=60)
    assert out == {"id": "9"}
    assert fake_queue.read_calls == [("WorkQ", 60, 2)]

async def test_dequeue_logs_and_returns_none_on_exception(sut, fake_queue, monkeypatch, caplog):
    async def boom(*a, **k): raise RuntimeError("read-fail")
    fake_queue.read_batch = boom
    out = await sut.dequeue()
    assert out is None
    assert any("Failed to dequeue job" in r.message for r in caplog.records)

# --------- complete_job ---------

async def test_complete_job_returns_false_and_traces_when_msg_id_missing(sut):
    tracer = FakeJobTracer()
    ok = await sut.complete_job({"queue_name": "q"}, job_tracer=tracer)
    assert ok is False
    assert tracer.errors and "No pgmq_msg_id" in tracer.errors[0]["summary"]

async def test_complete_job_success_calls_tracker_completed(sut, fake_queue):
    tracker = FakeJobTracker()
    ok = await sut.complete_job({"pgmq_msg_id": 11, "id": "11", "queue_name": "q"}, job_tracker_instance=tracker)
    assert ok is True
    assert fake_queue.deleted == [("q", 11)]
    assert tracker.completed_calls == 1

async def test_complete_job_still_true_if_tracker_completed_raises(sut, fake_queue):
    tracker = FakeJobTracker(fail_on={"completed"})
    ok = await sut.complete_job({"pgmq_msg_id": 12, "id": "12", "queue_name": "q"}, job_tracker_instance=tracker)
    assert ok is True
    assert tracker.completed_calls == 1

async def test_complete_job_false_when_delete_returns_false_and_traced(sut, fake_queue):
    fake_queue._delete_return = False
    tracer = FakeJobTracer()
    ok = await sut.complete_job({"pgmq_msg_id": 13, "id": "13", "queue_name": "q"}, job_tracer=tracer)
    assert ok is False
    assert tracer.errors and "Failed to mark job 13 as completed" in tracer.errors[0]["summary"]

async def test_complete_job_exception_path_returns_false_and_traces(sut, fake_queue):
    async def boom(*a, **k): raise RuntimeError("delete-fail")
    fake_queue.delete = boom
    tracer = FakeJobTracer()
    ok = await sut.complete_job({"pgmq_msg_id": 14, "id": "14", "queue_name": "q"}, job_tracer=tracer)
    assert ok is False
    assert tracer.errors and tracer.errors[0]["exc"] is not None

# --------- fail_job paths ---------

async def test_fail_job_missing_msg_id_returns_permanent_and_unhandled(sut):
    tracer = FakeJobTracer()
    perma, handled = await sut.fail_job({"id": "X"}, RuntimeError("boom"), job_tracer=tracer)
    assert (perma, handled) == (True, False)
    assert tracer.errors and tracer.errors[0]["summary"] == "Missing pgmq_msg_id"

@pytest.mark.parametrize("attempts,max_attempts,expected_delay", [
    (1, 3, 10),
    (2, 3, 20),
    (3, 5, 40),
    (6, 99, 300),  # capped
])
async def test_fail_job_retry_path_deletes_resends_and_calls_tracker_retry(sut, fake_queue, attempts, max_attempts, expected_delay, monkeypatch):
    job_data = {"pgmq_msg_id": 77, "id": "77", "queue_name": "Q", "attempts": attempts, "max_attempts": max_attempts}
    # Stabilize backoff to a known value by patching method to return expected_delay
    monkeypatch.setattr(sut, "_retry_delay_secs", lambda a: expected_delay)
    tracker = FakeJobTracker()
    perma, handled = await sut.fail_job(job_data, RuntimeError("err"), job_tracker_instance=tracker, error_trace="trace", retry=True)
    assert (perma, handled) == (False, True)
    # original deleted, new sent with delay
    assert fake_queue.deleted == [("Q", 77)]
    assert fake_queue.sent[0][0] == "Q"
    assert fake_queue.sent[0][2] == expected_delay
    assert tracker.retry_calls and tracker.retry_calls[0].isdigit()

async def test_fail_job_retry_logs_but_still_handles_if_tracker_retry_throws(sut, fake_queue, monkeypatch):
    job_data = {"pgmq_msg_id": 88, "id": "88", "queue_name": "Q", "attempts": 1, "max_attempts": 9}
    monkeypatch.setattr(sut, "_retry_delay_secs", lambda a: 10)
    tracker = FakeJobTracker(fail_on={"retry"})
    perma, handled = await sut.fail_job(job_data, RuntimeError("err"), job_tracker_instance=tracker, retry=True)
    assert (perma, handled) == (False, True)

async def test_fail_job_archive_path_calls_archive_tracker_fail_and_traces(sut, fake_queue):
    job_data = {"pgmq_msg_id": 99, "id": "99", "queue_name": "Q", "attempts": 3, "max_attempts": 3}
    tracer = FakeJobTracer()
    tracker = FakeJobTracker()
    perma, handled = await sut.fail_job(job_data, RuntimeError("kaput"), job_tracker_instance=tracker, job_tracer=tracer, retry=False)
    assert (perma, handled) == (True, True)
    assert fake_queue.archived == [("Q", 99)]
    assert tracker.fail_calls == ["99"]
    assert tracer.errors and "permanently failed" in tracer.errors[0]["summary"]

async def test_fail_job_archive_path_reports_unhandled_when_archive_fails(sut, fake_queue):
    fake_queue._archive_return = False
    job_data = {"pgmq_msg_id": 101, "id": "101", "queue_name": "Q", "attempts": 9, "max_attempts": 9}
    perma, handled = await sut.fail_job(job_data, RuntimeError("kaput"), retry=False)
    assert (perma, handled) == (True, False)

# --------- _should_retry & _retry_delay_secs ---------

@pytest.mark.parametrize("retry,attempts,max_attempts,expected", [
    (True, 0, 1, True),
    (True, 1, 1, False),
    (False, 1, 9, False),
])
def test_should_retry_logic(sut, retry, attempts, max_attempts, expected):
    assert sut._should_retry(retry, attempts, max_attempts) is expected

@pytest.mark.parametrize("attempts,expected", [
    (1, 10), (2, 20), (3, 40), (4, 80), (5, 160), (6, 300), (10, 300),
])
def test_retry_delay_progression_and_cap(sut, attempts, expected):
    assert sut._retry_delay_secs(attempts) == expected

# --------- _build_retry_payload ---------

def test_build_retry_payload_strips_ids_and_adds_error_fields(sut):
    job = {"id": "12", "pgmq_msg_id": 12, "attempts": 2, "foo": "bar"}
    err = ValueError("nope")
    out = sut._build_retry_payload(job, attempts=2, error=err, error_trace="stack")
    assert "id" not in out and "pgmq_msg_id" not in out
    assert out["attempts"] == 2 and out["retry_count"] == 2
    assert out["error_message"] == "nope" and out["last_error_trace"] == "stack"
    assert out["foo"] == "bar"

# --------- _archive_permanently (internal helper) ---------

async def test_archive_permanently_success_marks_tracker_and_tracer(sut, fake_queue):
    job_data = {"id": "5"}
    tracker = FakeJobTracker()
    tracer = FakeJobTracer()
    perma, handled = await sut._archive_permanently(queue_name="Q", msg_id=5, job_data=job_data,
                                                    attempts=3, error=RuntimeError("e"),
                                                    job_tracker_instance=tracker, job_tracer=tracer)
    assert (perma, handled) == (True, True)
    assert tracker.fail_calls == ["5"]
    assert tracer.errors and "permanently failed" in tracer.errors[0]["summary"]

async def test_archive_permanently_failure_reports_unhandled(sut, fake_queue):
    fake_queue._archive_return = False
    perma, handled = await sut._archive_permanently(queue_name="Q", msg_id=6, job_data={"id": "6"},
                                                    attempts=1, error=RuntimeError("e"),
                                                    job_tracker_instance=None, job_tracer=None)
    assert (perma, handled) == (True, False)

# --------- get_queue_stats ---------

async def test_get_queue_stats_happy_and_error(sut, fake_queue, caplog):
    fake_queue._metrics = FakeMetrics(queued=3, total=10, newest=7, oldest=99)
    stats = await sut.get_queue_stats("Q")
    assert stats == {"queued": 3, "total": 10, "newest_msg_age_sec": 7, "oldest_msg_age_sec": 99}

    async def boom(*a, **k): raise RuntimeError("metrics-fail")
    fake_queue.metrics = boom
    stats2 = await sut.get_queue_stats("Q")
    assert stats2 == {}
    assert any("Failed to get queue stats" in r.message for r in caplog.records)

# --------- close ---------

async def test_close_only_when_initialized(sut, fake_queue):
    sut._initialized = False
    await sut.close()
    assert fake_queue.closed == 0

    sut._initialized = True
    await sut.close()
    assert fake_queue.closed == 1
    assert sut._initialized is False
