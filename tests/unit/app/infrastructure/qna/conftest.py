import sys
import types
import importlib
from types import SimpleNamespace
import pytest

@pytest.fixture(autouse=True)
def stub_together_module(monkeypatch):
    """
    Some environments won't have the 'together' package installed.
    We stub it so importing qna_generator never fails.
    """
    dummy = types.ModuleType("together")
    class _DummyTogether: ...
    dummy.Together = _DummyTogether
    monkeypatch.setitem(sys.modules, "together", dummy)
    yield

@pytest.fixture
def qg(stub_together_module):
    """
    Import the module under test *after* stubbing external deps.
    """
    mod = importlib.import_module("app.infrastructure.qna.qna_generator")
    return mod

@pytest.fixture
def qutils():
    return importlib.import_module("app.infrastructure.qna.qna_utils")

@pytest.fixture
def qmodels():
    return importlib.import_module("app.infrastructure.qna.qna_models")

# ---- Fakes (prefer fakes/stubs over mocks) ----

class FakeTogetherResponse:
    def __init__(self, content: str):
        self.choices = [SimpleNamespace(message=SimpleNamespace(content=content))]

class _FakeCompletions:
    def __init__(self, *, content: str = "", raise_exc: bool = False, empty: bool = False):
        self._content = content
        self._raise = raise_exc
        self._empty = empty
    def create(self, **kwargs):
        if self._raise:
            raise RuntimeError("boom")
        return FakeTogetherResponse("" if self._empty else self._content)

class _FakeChat:
    def __init__(self, **kw):
        self.completions = _FakeCompletions(**kw)

class FakeTogetherClient:
    """
    Shape-compatible with what _ask_batch expects: client.chat.completions.create(...)
    """
    def __init__(self, **kw):
        self.chat = _FakeChat(**kw)

class FakeRepoObj:
    def __init__(self, analysis: str | None):
        self.repo_system_reference = analysis

class FakeRepoRepository:
    def __init__(self, analysis: str | None):
        self._analysis = analysis
        self.calls = []
    async def find_repo_by_id(self, _id: str):
        self.calls.append(("find_repo_by_id", _id))
        return FakeRepoObj(self._analysis)
