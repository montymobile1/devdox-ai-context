import pytest

from app.infrastructure.job_tracer.trace_formatter import build_error_chain_for_template, make_plain_stacktrace


# ---------- Fixtures for triggering exceptions ----------
def raise_simple_error():
    raise ValueError("basic error")

def raise_chained_error():
    try:
        raise KeyError("missing")
    except KeyError as ke:
        raise RuntimeError("top-level failure") from ke

def raise_contextual_error():
    try:
        raise IndexError("index out of range")
    except IndexError:
        try:
            raise TypeError("type issue")
        except TypeError as te:
            te.__suppress_context__ = True
            raise te


def raise_large_error():
    raise Exception("x" * 10000)


# ---------- Tests for build_error_chain_for_template ----------
def test_single_error_message():
    with pytest.raises(ValueError):
        raise_simple_error()

    try:
        raise_simple_error()
    except ValueError as e:
        chain = build_error_chain_for_template(e)

    assert len(chain) == 1
    node = chain[0]
    assert node["type"] == "ValueError"
    assert node["msg"] == "basic error"
    assert node["depth"] == 0
    assert node["func"] == "raise_simple_error"


def test_error_chain_with_cause():
    try:
        raise_chained_error()
    except RuntimeError as e:
        chain = build_error_chain_for_template(e)

    assert len(chain) == 2
    assert chain[0]["type"] == "KeyError"
    assert chain[1]["type"] == "RuntimeError"
    assert chain[0]["depth"] == 0
    assert chain[1]["depth"] == 1


def test_suppressed_context_error():
    try:
        raise_contextual_error()
    except TypeError as e:
        chain = build_error_chain_for_template(e)

    assert len(chain) == 1
    assert chain[0]["type"] == "TypeError"
    assert chain[0]["msg"] == "type issue"


def test_msg_truncation():
    try:
        raise Exception("A" * 500)
    except Exception as e:
        chain = build_error_chain_for_template(e, msg_limit=100)

    assert len(chain) == 1
    msg = chain[0]["msg"]
    assert msg.endswith("…")
    assert len(msg) == 100


def test_include_location_false():
    try:
        raise_simple_error()
    except ValueError as e:
        chain = build_error_chain_for_template(e, include_location=False)

    assert chain[0]["file"] is None
    assert chain[0]["line"] is None


# ---------- Tests for make_plain_stacktrace ----------
def test_make_plain_stacktrace_normal():
    try:
        raise_simple_error()
    except Exception as e:
        trace, truncated = make_plain_stacktrace(e)

    assert isinstance(trace, str)
    assert not truncated
    assert "ValueError: basic error" in trace


def test_make_plain_stacktrace_truncated():
    try:
        raise_large_error()
    except Exception as e:
        trace, truncated = make_plain_stacktrace(e, max_chars=200)

    assert truncated is True
    assert trace.endswith("…")
    assert len(trace) == 200


def test_make_plain_stacktrace_no_limit():
    try:
        raise_simple_error()
    except Exception as e:
        trace, truncated = make_plain_stacktrace(e, max_chars=0)

    assert not truncated