# tests/unit/assessment/test_qna_generator.py
import json
import re
import pytest
from types import SimpleNamespace

pytestmark = pytest.mark.unit

# --------------------
# Helper-level tests
# --------------------


def test_strip_code_fences(qg):
    fenced = "```json\n[{\"id\":\"goal\"}]\n```"
    assert qg._strip_code_fences(fenced) == '[{"id":"goal"}]'
    plain = '  [ {"id":"goal"} ]  '
    assert qg._strip_code_fences(plain) == '[ {"id":"goal"} ]'

@pytest.mark.parametrize("raw,expected", [
    (None, 0.0),
    ("0.9", 0.9),
    (2.5, 1.0),
    (-1, 0.0),
    ("oops", 0.0),
])
def test_normalize_confidence(qg, raw, expected):
    assert qg._normalize_confidence_score(raw) == pytest.approx(expected)

def test_chunk_splits_even_and_remainder(qg):
    lst = [(str(i), f"Q{i}") for i in range(9)]
    chunks = qg._chunk(lst, 4)
    assert chunks == [
        lst[0:4],
        lst[4:8],
        lst[8:9],
    ]

def test_build_prompt_has_analysis_and_questions(qg):
    analysis = "Repo does X. Evidence: Y."
    qs = [("goal","What is the main goal?"), ("maturity","How mature?")]
    prompt = qg._build_qna_prompt(analysis, qs)
    # Don’t assert the entire string (brittle); assert critical invariants.
    assert "ANALYSIS" in prompt and analysis in prompt
    assert "QUESTIONS" in prompt
    assert json.dumps([{"id":"goal","question":"What is the main goal?"},
                       {"id":"maturity","question":"How mature?"}], ensure_ascii=False) in prompt

class TestParseQnaJson:

    def test_parse_qna_json_happy_path(self, qg, qutils):
        questions = [("goal","G?"), ("maturity","M?")]
        raw = json.dumps([
            {"id":"goal","question":"G?","answer":"A1","confidence":0.7,
             "insufficient_evidence":"no","evidence_snippets":["a","b","c"]},
            {"id":"maturity","question":"M?","answer":"A2","confidence":"0.9",
             "insufficient_evidence":"yes","evidence_snippets":"not-a-list"},
        ])
        pairs = qg._parse_qna_json_response(raw, questions)
        assert [p.id for p in pairs] == ["goal","maturity"]
        g, m = pairs
        assert g.answer == "A1" and pytest.approx(g.confidence) == 0.7 and g.insufficient_evidence is False
        assert len(g.evidence_snippets) == 2 and g.evidence_snippets[0] == "a"
        assert m.insufficient_evidence is True and m.evidence_snippets == []
    
    def test_parse_qna_json_handles_fenced_and_missing_items(self, qg):
        questions = [("goal","G?"), ("maturity","M?"), ("extra","E?")]
        fenced = "```json\n" + json.dumps([
            {"id":"goal","question":"G?","answer":"A1","confidence":1,"insufficient_evidence":0,
             "evidence_snippets":["q"]},
            # omit 'maturity' to force placeholder
        ]) + "\n```"
        pairs = qg._parse_qna_json_response(fenced, questions)
        # parser returns items it saw + placeholders for unseen
        by_id = {p.id: p for p in pairs}
        assert by_id["goal"].answer == "A1"
        assert by_id["maturity"].answer == qg.NO_ANSWER
        assert by_id["maturity"].insufficient_evidence is True
        assert by_id["extra"].answer == qg.NO_ANSWER
    
    def test_parse_qna_json_total_malformed_falls_back(self, qg):
        questions = [("q1","?"), ("q2","?")]
        not_json = "<<< model went rogue >>>" * 50
        pairs = qg._parse_qna_json_response(not_json, questions)
        assert len(pairs) == 2
        assert all(p.insufficient_evidence for p in pairs)
        # raw stuffed into answer (truncated)
        assert pairs[0].answer.startswith("<<< model went rogue >>>")

class TestAskBatch:
    def test_ask_batch_success(self, qg):
        qs = [("goal","G?")]
        analysis = "Some analysis text."
        content = json.dumps([{
            "id":"goal","question":"G?","answer":"A","confidence":0.5,
            "insufficient_evidence": False, "evidence_snippets":["e1"]
        }])
        client = SimpleNamespace(chat=SimpleNamespace(
            completions=SimpleNamespace(create=lambda **kw: SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=content))]))
        ))
        pairs, prompt, raw = qg._ask_batch(client, "model", analysis, qs, temperature=0.1, max_tokens=64)
        assert pairs and pairs[0].id == "goal"
        assert "ANALYSIS" in prompt
        assert raw.strip().startswith("[")
    
    def test_ask_batch_api_error_returns_placeholders_and_audit(self, qg):
        qs = [("goal", "G?")]
        
        # Force the API call to raise
        client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(
                    create=lambda **kw: (_ for _ in ()).throw(RuntimeError("X"))
                )
            )
        )
        
        pairs, _, raw = qg._ask_batch(
            client, "m", "A", qs, temperature=0.1, max_tokens=64
        )
        
        # Behavior: stable output shape → placeholders, not empty
        assert [p.id for p in pairs] == ["goal"]
        assert pairs[0].answer == qg.NO_ANSWER
        assert pairs[0].insufficient_evidence is True
        assert pairs[0].question == "G?"
        assert "ERROR calling model:" in raw
    
    def test_ask_batch_empty_content_returns_placeholders_and_audit(self, qg):
        qs = [("goal", "G?")]
        
        client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(
                    create=lambda **kw: SimpleNamespace(
                        choices=[SimpleNamespace(message=SimpleNamespace(content=""))]
                    )
                )
            )
        )
        
        pairs, _, raw = qg._ask_batch(
            client, "m", "A", qs, temperature=0.1, max_tokens=64
        )
        
        assert [p.id for p in pairs] == ["goal"]
        assert pairs[0].answer == qg.NO_ANSWER
        assert pairs[0].insufficient_evidence is True
        assert "(empty content from model)" in raw
    
# --------------------
# Public API: generate_project_qna
# --------------------

class TestGenerateProjectQna:
    @pytest.mark.asyncio
    async def test_generate_qna_no_analysis_returns_placeholders(self, qg, qmodels):
        repo = SimpleNamespace(repo_system_reference=None)
        class RepoStub:
            async def find_repo_by_id(self, id): return repo
        pkg = await qg.generate_project_qna(
            id_for_repo="1", project_name="P", repo_url="U",
            together_client=SimpleNamespace(), repo_repository=RepoStub(),
            questions=[("q1","?"), ("q2","?")]
        )
        assert [p.id for p in pkg.pairs] == ["q1","q2"]
        assert all(p.insufficient_evidence for p in pkg.pairs)
        assert all(p.answer == "(no analysis available)" for p in pkg.pairs)
        assert pkg.raw_prompt is None and pkg.raw_response is None
    
    @pytest.mark.asyncio
    async def test_generate_qna_batches_merge_and_order(self, qg, qmodels):
        # Make 5 questions, batch_size=2 → 3 batches
        questions = [("q1","Q1?"), ("q2","Q2?"), ("q3","Q3?"), ("q4","Q4?"), ("q5","Q5?")]
        # Return JSON that answers only q1 and q4 → others filled by placeholders
        def mk_resp(ids):
            arr = []
            for qid in ids:
                if qid in {"q1","q4"}:
                    arr.append({"id": qid, "question": f"{qid.upper()}?", "answer": f"A_{qid}",
                                "confidence": 0.8, "insufficient_evidence": False, "evidence_snippets": ["s"]})
            return json.dumps(arr)
        class SmartFake:
            def __init__(self):
                self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))
            def create(self, *, messages, **_):
                prompt = messages[0]["content"]
                # Extract question IDs from the QUESTIONS JSON in the prompt.
                m = re.search(r"QUESTIONS\s*-+\s*(\[[\s\S]*\])\s*-+", prompt)
                ids = [d["id"] for d in json.loads(m.group(1))]
                content = mk_resp(ids)
                return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])
    
        repo = SimpleNamespace(repo_system_reference="Analysis text here.")
        class RepoStub:
            async def find_repo_by_id(self, id): return repo
    
        pkg = await qg.generate_project_qna(
            id_for_repo="R1", project_name="Proj", repo_url="url",
            together_client=SmartFake(), repo_repository=RepoStub(),
            questions=questions, batch_size=2
        )
        # Order must match input questions regardless of model order
        assert [p.id for p in pkg.pairs] == [qid for (qid, _) in questions]
        by = {p.id: p for p in pkg.pairs}
        assert by["q1"].answer == "A_q1" and by["q4"].answer == "A_q4"
        assert by["q2"].answer == qg.NO_ANSWER and by["q2"].insufficient_evidence is True
        # 3 batches => 3 sections in raw_prompt/raw_response
        assert pkg.raw_prompt.count("--- BATCH ") == 3
        assert pkg.raw_response.count("--- BATCH ") == 3
    
    @pytest.mark.asyncio
    async def test_generate_qna_truncates_analysis_in_prompt(self, qg):
        analysis = "A" * 1000
        repo = SimpleNamespace(repo_system_reference=analysis)
        class RepoStub:
            async def find_repo_by_id(self, id): return repo
        # Fake model returns empty content → placeholders
        class EmptyModel:
            def __init__(self): self.chat = SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=""))])))
        pkg = await qg.generate_project_qna(
            id_for_repo="1", project_name="P", repo_url="U",
            together_client=EmptyModel(), repo_repository=RepoStub(),
            questions=[("q","?")], truncate_chars=123
        )
        assert "ANALYSIS" in pkg.raw_prompt
        # ensure truncated: analysis length in prompt body ≤ 123 + headers
        assert "A" * 200 not in pkg.raw_prompt
    
    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad", [0, -1])
    async def test_generate_qna_invalid_batch_size_raises(self, qg, bad):
        with pytest.raises(ValueError):
            await qg.generate_project_qna(
                id_for_repo="x", project_name="p", repo_url="u",
                together_client=None, repo_repository=None,
                batch_size=bad
            )
    
    @pytest.mark.asyncio
    async def test_generate_qna_when_internal_ask_batch_raises_use_placeholders_and_audit(self, qg, monkeypatch):
        # Force the rare fallback branch by making _ask_batch itself raise.
        def boom(*a, **k): raise RuntimeError("kaboom")
        monkeypatch.setattr(qg, "_ask_batch", boom)
        repo = SimpleNamespace(repo_system_reference="A")
        class RepoStub:
            async def find_repo_by_id(self, id): return repo
        pkg = await qg.generate_project_qna(
            id_for_repo="1", project_name="P", repo_url="U",
            together_client=None, repo_repository=RepoStub(),
            questions=[("q1","?"), ("q2","?")], batch_size=2
        )
        assert all(p.answer == qg.NO_ANSWER and p.insufficient_evidence for p in pkg.pairs)
        assert "ERROR in _ask_batch:" in pkg.raw_response
