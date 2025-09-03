import pytest

class TestSnipperCalculator:
    def test_snippet_calculator_clips_and_limits(self, qutils) -> None:
        long = "x" * (qutils.MAX_SNIPPET_CHARS + 50)
        out = qutils.snippet_calculator([long, 12345, "ok", "ignored"])
        assert len(out) == 2
        # first item is clipped with ellipsis; second coerced to str
        assert out[0].endswith("…")
        assert len(out[0]) == qutils.MAX_SNIPPET_CHARS
        assert out[1] == "12345"

class TestToBool:
    @pytest.mark.parametrize("val,expected", [
        (True, True), (False, False),
        (1, True), (0, False), (2, True), (-1, True),
        ("YES", True), (" y ", True), ("True", True), ("t", True),
        ("NO", False), ("n", False), ("false", False), ("0", False),
    ])
    def test__to_bool_truthy_falsy(self, qutils, val, expected) -> None:
        assert qutils._to_bool(val) is expected
    
    def test__to_bool_default_on_unknown(self, qutils) -> None:
        assert qutils._to_bool("maybe") is False
        assert qutils._to_bool("maybe", default=True) is True
