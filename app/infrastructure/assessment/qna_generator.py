"""
Build concise, developer-oriented Q&A from an existing repository analysis.

High-level design
-----------------
This module takes a *long form* analysis you already stored for a repo (e.g., in
`repo.repo_system_reference`), asks an LLM a small set of targeted questions, and
returns a structured `ProjectQnAPackage` ready for downstream use (email, API, UI,
etc.). It deliberately **does not** send emails—this keeps Q&A generation loosely
coupled from delivery.

Key traits
- Simple integration: call `generate_project_qna(...)` after your main analysis
  step succeeds; you get back a clean object of typed `QAPair`s.
- Stable output shape: always returns all requested questions, even when the LLM
  misbehaves (fallbacks are applied).
- Token-safe: questions are asked in *batches* to avoid long, truncated replies.
- Evidence hygiene: the prompt asks for up to two *verbatim* evidence snippets
  from your analysis and clearly marks *inference* vs *direct evidence* using:
  - `"Inferred: "` prefix in the answer
  - lower `confidence` (≤ 0.6) for inferred answers
  - `insufficient_evidence=True` when the model can’t even infer

How to use
----------
1) Ensure your analysis text is saved (e.g., `repo.repo_system_reference`).
2) Call `generate_project_qna(...)` with:
   - the repo id (DB primary key),
   - project name & URL (for packaging),
   - your Together client instance,
   - a repository helper exposing `.find_repo_by_id(id) -> repo`.
3) You’ll get back a `ProjectQnAPackage` (see qna_models.py) with:
   - ordered `pairs: list[QAPair]`
   - `raw_prompt`/`raw_response` (concatenated across batches for observability)

Swapping question sources
-------------------------
Questions are currently hardcoded in `DEFAULT_QUESTIONS` (ID + text). You can:
- Pass your own `questions=[(...), ...]` to `generate_project_qna`, or
- Replace `DEFAULT_QUESTIONS` at import time, or
- Pull from a DB, then pass that list in.

This file intentionally contains **no** database logic beyond reading the repo
analysis and **no** email code. It’s a single responsibility “Q&A packer”.
"""
from __future__ import annotations
import json
import logging
import re
from typing import Dict, List, Tuple, Optional

from app.infrastructure.database.repositories import RepoRepositoryHelper

from .qna_models import QAPair, ProjectQnAPackage

logger = logging.getLogger(__name__)

# Default questions live here (easy to swap for a DB later)
DEFAULT_QUESTIONS: List[Tuple[str, str]] = [
    ("goal", "What is the main goal of this project?"),
    ("uniqueness", "What makes this project unique compared to others like it?"),
    ("onboarding", "How well does this project communicate to new joiners who it’s for, and can someone quickly find their way around?"),
    ("maturity", "How mature is the project right now (early stage vs stable)?"),
    
    # Added to check what they will return
    ("organization", "Is the project well organized at a glance?"),
    ("findability", "Can someone quickly find their way around?"),
    ("evolution_cleanliness", "Does it look like the project has grown in a clean way?"),
    ("communication_or_maintainability", "Does the project look well-communicated overall, or appear maintainable in the long run?"),
    ("continuous_improvement", "Is there a pattern of continuous improvement?"),
    ("weight_feel", "Does the project feel lightweight and clean, or heavy and messy?"),
    ("test_reliability", "How reliable does the project appear based on its testing setup?")
]

# ---------------------------
# Helpers / constants
# ---------------------------

def _build_qna_prompt(analysis_text: str, questions: list[tuple[str, str]]) -> str:
    """
    Build a strict, JSON-only prompt tailored for senior developers.

    The prompt:
      - Forces a fixed JSON shape (id/question/answer/confidence/insufficient_evidence/evidence_snippets)
      - Encourages direct evidence; allows inference (with a visible "Inferred: " prefix)
      - Demands up to two *verbatim* snippets from ANALYSIS, or [] if none exist
      - Forbids markdown/backticks/extra text (reduces parse headaches)

    Args:
        analysis_text: The long analysis previously generated & stored for the repo.
        questions: List of (id, question) tuples in the order you want answers returned.

    Returns:
        A single string prompt to send to the LLM.
    """
    import json
    qlist = [{"id": qid, "question": q} for qid, q in questions]
    qjson = json.dumps(qlist, ensure_ascii=False)

    return f"""
You are analyzing ANALYSIS text about a software repository for an experienced software developer audience.

TASK
- Answer each question concisely in 2–4 sentences using precise, technical language.
- Base answers ONLY on the ANALYSIS text.
- You MAY infer likely intent/purpose if the evidence is indirect. When you infer, start the answer with "Inferred: " and set confidence ≤ 0.6.
- If there is not enough basis to even infer, set insufficient_evidence = true and answer briefly (e.g., "Not enough information in the analysis to determine this.").
- For each answer, include up to 2 very short verbatim evidence snippets copied from ANALYSIS that support the answer. If you inferred and no direct quote exists, use an empty list [].

OUTPUT
Return ONLY valid JSON (no Markdown, no backticks, no extra text).
It MUST be a JSON array where each item has this exact shape:
{{
  "id": "<exact id from input>",
  "question": "<exact question from input>",
  "answer": "<2–4 sentences; prefix with 'Inferred: ' when inferring>",
  "confidence": <number between 0 and 1>,
  "insufficient_evidence": <true|false>,
  "evidence_snippets": ["<short verbatim quote from ANALYSIS>", "<optional second quote>"]
}}

RULES
- Keep answers in the SAME ORDER as the provided questions and copy IDs exactly.
- Do NOT fabricate quotes; if none exist, use [].
- Keep claims precise; avoid generic marketing language.
- If the ANALYSIS is ambiguous or contradictory, note the uncertainty and lower confidence accordingly.

ANALYSIS
---------
{analysis_text}
---------

QUESTIONS
---------
{qjson}
---------
""".strip()

def _strip_code_fences(text: str) -> str:
    """
    Remove accidental Markdown code fences that some models include around JSON.
    Args:
        text: Raw LLM output.
    Returns:
        The inner JSON if fenced, otherwise a trimmed original string.
    """
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    return m.group(1).strip() if m else text.strip()

def _normalize_confidence_score(x: float | None) -> float:
    """
    Coerce a value into [0.0, 1.0]. Non-numeric/None falls back to 0.0.

    Args:
        x: Any numeric value or None.

    Returns:
        A float in [0.0, 1.0].
    """
    try:
        return max(0.0, min(1.0, float(x)))
    except Exception:
        return 0.0

def _parse_qna_json_response(raw: str, questions: List[Tuple[str, str]]) -> List[QAPair]:
    """
    Parse the model’s JSON into typed `QAPair`s, leniently.

    - Strips code fences if present.
    - Validates array shape, tolerates missing fields.
    - Ensures *every* requested question appears in output (fills gaps with
      a “(no answer)” placeholder and `insufficient_evidence=True`).
    - Truncates/normalizes `evidence_snippets` to max 2 items.

    Args:
        raw: Raw JSON (or JSON-like) text from the LLM.
        questions: The (id, question) pairs requested, in order.

    Returns:
        List of `QAPair` in the same order as `questions`.
    """
    
    raw = _strip_code_fences(raw)
    by_id: Dict[str, str] = {qid: q for qid, q in questions}
    out: List[QAPair] = []

    try:
        data = json.loads(raw)
        if not isinstance(data, list):
            raise ValueError("Expected a JSON array")

        seen = set()
        for item in data:
            qid = (item.get("id") or "").strip()
            if not qid:
                continue
            question = (item.get("question") or by_id.get(qid, "")).strip()
            answer = (item.get("answer") or "").strip()
            if not question or not answer:
                continue

            conf = _normalize_confidence_score(item.get("confidence"))
            insuff = bool(item.get("insufficient_evidence", False))
            snippets = item.get("evidence_snippets") or []
            # normalize snippets to <=2 strings
            if isinstance(snippets, list):
                snippets = [str(s) for s in snippets][:2]
            else:
                snippets = []

            out.append(QAPair(
                id=qid,
                question=question,
                answer=answer,
                confidence=conf,
                insufficient_evidence=insuff,
                evidence_snippets=snippets,
            ))
            seen.add(qid)

        # ensure we have an entry for every asked question
        for qid, q in questions:
            if qid not in seen:
                out.append(QAPair(
                    id=qid,
                    question=q,
                    answer="(no answer)",
                    confidence=0.0,
                    insufficient_evidence=True,
                    evidence_snippets=[],
                ))
        return out

    except Exception:
        # Last-ditch fallback: stuff the raw into every answer
        return [
            QAPair(id=qid, question=q, answer=raw[:1200],
                   confidence=0.0, insufficient_evidence=True, evidence_snippets=[])
            for qid, q in questions
        ]

def _chunk(lst: List[Tuple[str, str]], n: int) -> List[List[Tuple[str, str]]]:
    """
    Split a list into fixed-size chunks.

    Used to ask smaller batches of questions to reduce the risk of the model
    truncating its JSON response.

    Args:
        lst: Full list of (id, question) tuples.
        n: Chunk size.

    Returns:
        A list of sublists, each of size up to `n`.
    """
    
    return [lst[i:i+n] for i in range(0, len(lst), n)]

def _ask_batch(
    together_client,
    model: str,
    analysis_text: str,
    qs: List[Tuple[str, str]],
    *,
    temperature: float,
    max_tokens: int,
) -> tuple[List[QAPair], str, str]:
    """
    Ask the model a *subset* of questions (one batch).

    Args:
        together_client: An instance compatible with Together’s Python SDK,
            exposing `.chat.completions.create(model=..., messages=[...], ...)`.
        model: Model name (e.g., "meta-llama/Llama-3.3-70B-Instruct-Turbo").
        analysis_text: The repo analysis being used as the only evidence base.
        qs: The (id, question) tuples in this batch.
        temperature: Decoding temperature.
        max_tokens: Max generation tokens for this batch.

    Returns:
        (pairs, prompt, raw_json)
        - pairs: Parsed `QAPair`s
        - prompt: The exact prompt sent (for observability/debugging)
        - raw_json: The raw model response content (for observability/debugging)
    """
    prompt = _build_qna_prompt(analysis_text, qs)
    resp = together_client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=temperature,
        top_p=0.9,
    )
    raw = resp.choices[0].message.content
    return _parse_qna_json_response(raw, qs), prompt, raw

# --------------------------------------------
# Public API (pure function returning QnA data)
# --------------------------------------------
async def generate_project_qna(
    *,
    id_for_repo: str,
    project_name: str,
    repo_url: str,
    together_client,
    repo_repository,
    questions: Optional[List[Tuple[str, str]]] = None,
    model: str = "meta-llama/Llama-3.3-70B-Instruct-Turbo",
    temperature: float = 0.2,
    max_tokens: int = 1200,
    truncate_chars: int = 12000, # keep prompt sane
    batch_size: int = 4 # ask 4 at a time
) -> ProjectQnAPackage:
    """
    Build a `ProjectQnAPackage` from your existing long-form repo analysis.

    This is the only function most callers need. It reads the repo’s saved analysis,
    asks the LLM the provided (or default) questions in *batches*, and returns a
    packaged, stable object that downstream systems can render or email.

    Separation of concerns
    - This function **does not** send email.
    - It only produces structured Q&A artifacts for later consumption.

    Args:
        id_for_repo: Your DB primary key for the repo (used to fetch the analysis).
        project_name: Human-readable project name for packaging/headers.
        repo_url: Repo URL (included in the package for display/use later).
        together_client: Together SDK client instance (already configured with API key).
        repo_repository: Object exposing `find_repo_by_id(id)` -> repo with `repo_system_reference`.
        questions: Optional override list of (id, question) tuples (default: `DEFAULT_QUESTIONS`).
        model: Together model name.
        temperature: Decoding temperature.
        max_tokens: Max generation tokens per **batch** (not the whole job).
        truncate_chars: Hard cap for analysis length used in the prompt to avoid overlong inputs.
        batch_size: How many questions to ask per LLM call (controls truncation risk).

    Returns:
        ProjectQnAPackage with:
          - `pairs`: ordered list of `QAPair`s (one per requested question)
          - `model`: model name used
          - `raw_prompt`/`raw_response`: concatenated strings for all batches
            (useful for audits/observability)

    Notes:
        - If the repo has no analysis text, returns placeholders with
          `insufficient_evidence=True`.
        - If the model’s JSON is malformed, a lenient parser ensures you still
          get a well-formed `ProjectQnAPackage` with sensible defaults.
    """
    questions = questions or DEFAULT_QUESTIONS

    repo = await repo_repository.find_repo_by_id(id_for_repo)
    analysis_text = (getattr(repo, "repo_system_reference", None) or "").strip()

    if not analysis_text:
        pairs = [QAPair(id=qid, question=q, answer="(no analysis available)",
                        confidence=0.0, insufficient_evidence=True, evidence_snippets=[])
                 for qid, q in questions]
        return ProjectQnAPackage(
            project_name=project_name,
            repo_url=repo_url,
            repo_id=id_for_repo,
            pairs=pairs,
            model=model,
            raw_prompt=None,
            raw_response=None,
        )

    if truncate_chars and len(analysis_text) > truncate_chars:
        analysis_text = analysis_text[:truncate_chars]

    # Ask in batches to avoid cutoff
    raw_prompts: List[str] = []
    raw_responses: List[str] = []
    
    merged: Dict[str, QAPair] = {}
    for i, chunk_qs in enumerate(_chunk(questions, batch_size), start=1):
        chunk_pairs, prompt, raw = _ask_batch(
            together_client, model, analysis_text, chunk_qs,
            temperature=temperature, max_tokens=max_tokens
        )
        raw_prompts.append(f"--- BATCH {i} PROMPT ---\n{prompt}")
        raw_responses.append(f"--- BATCH {i} RESPONSE ---\n{raw}")
        for p in chunk_pairs:
            merged[p.id] = p
    
    ordered_pairs = [merged.get(qid) or QAPair(
        id=qid, question=q, answer="(no answer)",
        confidence=0.0, insufficient_evidence=True, evidence_snippets=[]
    ) for qid, q in questions]
    
    return ProjectQnAPackage(
        project_name=project_name,
        repo_url=repo_url,
        repo_id=id_for_repo,
        pairs=ordered_pairs,
        model=model,
        raw_prompt="\n\n".join(raw_prompts),
        raw_response="\n\n".join(raw_responses),
    )