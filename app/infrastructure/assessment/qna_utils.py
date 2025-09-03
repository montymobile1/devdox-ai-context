from typing import List

from app.infrastructure.assessment.qna_models import FALSY, MAX_SNIPPET_CHARS, TRUTHY


def snippet_calculator(raw_snippets:List[str]) -> list[str]:
    def _clip(s: object, n: int) -> str:
        s = str(s)
        return s if len(s) <= n else s[: max(0, n - 1)] + "…"

    return [_clip(s, MAX_SNIPPET_CHARS) for s in raw_snippets][:2]

def _to_bool(v, default: bool = False) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        # 0 -> False, anything else -> True
        return bool(v)
    if v is None:
        return default
    s = str(v).strip().lower()
    if s in TRUTHY:
        return True
    if s in FALSY:
        return False
    return default