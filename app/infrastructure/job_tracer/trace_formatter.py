from __future__ import annotations
import os
import traceback
from typing import List, Dict, Any, Tuple


def _exc_message(te: traceback.TracebackException) -> str:
    """
    Extract message from TracebackException.
    "ZeroDivisionError: division by zero" -> "division by zero"
    """
    exc_only = "".join(te.format_exception_only()).strip()
    if ": " in exc_only:
        return exc_only.split(": ", 1)[1].strip()
    return exc_only


def build_error_chain_for_template(
    exc: BaseException,
    *,
    include_location: bool = True,
    msg_limit: int = 200,
) -> List[Dict[str, Any]]:
    """
    Returns OUTER→INNER nodes for top-down display.
    Each node: {depth, func, type, msg, file, line}
    """
    te = traceback.TracebackException.from_exception(exc)
    chain: List[Dict[str, Any]] = []

    cur = te
    while cur:
        # Where THIS exception was raised (last frame of its stack)
        if cur.stack:
            frame = cur.stack[-1]
            func = frame.name
            filename = os.path.basename(frame.filename) if include_location else None
            lineno = frame.lineno if include_location else None
        else:
            func, filename, lineno = "<unknown>", None, None

        exc_type = getattr(cur, "exc_type", None)
        type_name = getattr(exc_type, "__name__", getattr(cur, "exc_type_name", "Exception"))
        msg = _exc_message(cur)

        if msg_limit and len(msg) > msg_limit:
            msg = msg[: msg_limit - 1] + "…"

        chain.append(
            {
                "func": func,
                "type": type_name,
                "msg": msg,
                "file": filename,
                "line": lineno,
            }
        )

        # Prefer explicit causes; fall back to context (unless suppressed)
        cur = cur.__cause__ or (None if cur.__suppress_context__ else cur.__context__)

    # Reverse to OUTER→INNER and assign depth
    chain = list(reversed(chain))
    for i, node in enumerate(chain):
        node["depth"] = i
    return chain


def make_plain_stacktrace(
    exc: BaseException, *, max_chars: int = 16000
) -> Tuple[str, bool]:
    """
    Returns (stacktrace_text, truncated_flag).
    """
    text = "".join(traceback.format_exception(exc))
    truncated = False
    if max_chars and len(text) > max_chars:
        text = text[: max_chars - 1] + "…"
        truncated = True
    return text, truncated
