import pytest
from app.infrastructure.mailing_service.test_doubles.base import (
    CallSpyMixin, ExceptionPlanMixin, FakeBase
)

# -------- tiny concrete helpers local to the test module --------
class _SpyOnly(CallSpyMixin):
    def __init__(self): super().__init__()
    def ping(self, *args, **kw): return self._touch(self.ping, *args, **kw)
    def pong(self, *args, **kw): return self._touch(self.pong, *args, **kw)

class _FakeForBefore(FakeBase):
    def __init__(self): super().__init__()
    def op(self, *args, **kw): return self._before(self.op, *args, **kw)
    def op2(self, *args, **kw): return self._before(self.op2, *args, **kw)

class _ExcOnly(ExceptionPlanMixin):
    def __init__(self): super().__init__()
    def danger(self):
        self._maybe_raise("danger")
        return "ok"

# -------------------- grouped tests --------------------

class TestCallSpyMixin:
    @pytest.fixture
    def spy(self):
        return _SpyOnly()

    def test_records_and_returns_name(self, spy):
        assert spy.ping(1, y=2) == "ping"
        assert spy.received_calls == [("ping", (1,), {"y": 2})]

    def test_multiple_calls_order(self, spy):
        spy.ping(10); spy.pong(a="A"); spy.ping(20, b="B")
        assert spy.received_calls == [
            ("ping", (10,), {}),
            ("pong", (), {"a": "A"}),
            ("ping", (20,), {"b": "B"}),
        ]


class TestExceptionPlanViaFakeBase:
    @pytest.fixture
    def fake(self):
        return _FakeForBefore()

    def test_before_records_then_raises(self, fake):
        fake.set_exception(_FakeForBefore.op, RuntimeError("boom"))
        with pytest.raises(RuntimeError, match="boom"):
            fake.op(42, k="v")
        assert fake.received_calls == [("op", (42,), {"k": "v"})]

    def test_before_returns_name_when_not_planned(self, fake):
        assert fake.op(1, x=2) == "op"
        assert fake.received_calls == [("op", (1,), {"x": 2})]

    def test_exception_scoped_per_method(self, fake):
        fake.set_exception(_FakeForBefore.op, ValueError("x"))
        assert fake.op2("safe") == "op2"
        with pytest.raises(ValueError):
            fake.op("fail")
        assert fake.received_calls == [
            ("op2", ("safe",), {}),
            ("op", ("fail",), {}),
        ]


class TestExceptionPlanMixinIsolation:
    @pytest.fixture
    def exc_only(self):
        return _ExcOnly()

    def test_raise_by_method_name(self, exc_only):
        exc_only.set_exception(_ExcOnly.danger, KeyError("nope"))
        with pytest.raises(KeyError, match="nope"):
            exc_only.danger()

    def test_no_raise_when_unplanned(self, exc_only):
        assert exc_only.danger() == "ok"


class TestInitializationInvariants:
    @pytest.fixture
    def fake(self):
        return _FakeForBefore()

    def test_fakebase_init_wires_mixins(self, fake):
        assert hasattr(fake, "received_calls") and fake.received_calls == []
        assert hasattr(fake, "_exceptions") and fake._exceptions == {}

    def test_before_returns_method_name_without_exception(self, fake):
        assert fake.op(k=1) == "op"
