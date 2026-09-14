from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cv_ranker.llm_client import LLMClient, LLMClientError
from cv_ranker.parsing import ParsedCV, iter_cv_files, parse_cv_file

SYSTEM_PROMPT = (
    "You are a strict technical recruiter assistant. "
    "Given candidate CV text and job requirements, return a JSON object only with fields: "
    "score (0..100 integer), matched_skills (array of strings), missing_skills (array of strings), "
    "years_experience (number), summary (string <= 220 chars)."
)


@dataclass
class CandidateScore:
    filename: str
    score: int
    matched_skills: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)
    years_experience: float = 0.0
    summary: str = ""
    warnings: list[str] = field(default_factory=list)


@dataclass
class RankConfig:
    requirements: str
    mode: str = "auto"  # auto | llm | heuristic
    top_k: int = 0


class CVRanker:
    def __init__(self, llm_client: LLMClient | None = None):
        self.llm_client = llm_client

    def rank_folder(self, folder: Path, config: RankConfig) -> list[CandidateScore]:
        if not folder.exists() or not folder.is_dir():
            raise ValueError(f"CV folder does not exist or is not a folder: {folder}")

        parsed_cvs = [parse_cv_file(path) for path in iter_cv_files(folder)]
        scores = [self.score_candidate(parsed_cv, config) for parsed_cv in parsed_cvs]
        scores.sort(key=lambda c: (-c.score, c.filename.lower()))

        if config.top_k > 0:
            return scores[: config.top_k]
        return scores

    def score_candidate(self, parsed_cv: ParsedCV, config: RankConfig) -> CandidateScore:
        warnings = list(parsed_cv.warnings)
        filename = parsed_cv.file_path.name
        cv_text = parsed_cv.text.strip()

        if not cv_text:
            return CandidateScore(
                filename=filename,
                score=0,
                summary="No extractable text from CV.",
                warnings=warnings,
            )

        if config.mode in {"auto", "llm"} and self.llm_client:
            try:
                llm_score = self._score_with_llm(filename, cv_text, config.requirements)
                llm_score.warnings.extend(warnings)
                return llm_score
            except (LLMClientError, ValueError) as exc:
                if config.mode == "llm":
                    return CandidateScore(
                        filename=filename,
                        score=0,
                        summary="LLM scoring failed.",
                        warnings=[*warnings, str(exc)],
                    )
                warnings.append(f"Falling back to heuristic scoring: {exc}")

        heuristic = self._score_with_heuristic(filename, cv_text, config.requirements)
        heuristic.warnings.extend(warnings)
        return heuristic

    def _score_with_llm(self, filename: str, cv_text: str, requirements: str) -> CandidateScore:
        prompt = f"Job requirements:\n{requirements}\n\nCandidate CV:\n{cv_text}\n\nReturn strict JSON only."

        assert self.llm_client is not None
        response = self.llm_client.generate(prompt=prompt, system=SYSTEM_PROMPT)
        data = _parse_json_from_response(response)

        score = _clamp_score(data.get("score", 0))
        matched = _normalize_skill_list(data.get("matched_skills", []))
        missing = _normalize_skill_list(data.get("missing_skills", []))
        years = _to_float(data.get("years_experience", 0))
        summary = str(data.get("summary", "")).strip()[:220]

        return CandidateScore(
            filename=filename,
            score=score,
            matched_skills=matched,
            missing_skills=missing,
            years_experience=years,
            summary=summary or "Scored by LLM.",
        )

    def _score_with_heuristic(self, filename: str, cv_text: str, requirements: str) -> CandidateScore:
        required_skills = _extract_required_skills(requirements)
        required_years = _extract_required_years(requirements)

        cv_lower = cv_text.lower()
        matched = [skill for skill in required_skills if skill.lower() in cv_lower]
        missing = [skill for skill in required_skills if skill not in matched]

        # Skills are the strongest signal for this fallback score.
        skill_score = (len(matched) / len(required_skills) * 80) if required_skills else 0

        cv_years = _extract_candidate_years(cv_text)
        if required_years > 0:
            exp_ratio = min(cv_years / required_years, 1.0)
            exp_score = exp_ratio * 20
        else:
            exp_score = 0

        total = round(skill_score + exp_score)
        total = _clamp_score(total)

        if not matched and (required_years <= 0 or cv_years <= 0):
            total = 0

        summary = (
            f"Heuristic score based on {len(matched)}/{len(required_skills)} required skills"
            f" and {cv_years:.1f} years experience estimate."
        )

        return CandidateScore(
            filename=filename,
            score=total,
            matched_skills=matched,
            missing_skills=missing,
            years_experience=cv_years,
            summary=summary,
        )


def _parse_json_from_response(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError("No JSON object found in model response")

    parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise ValueError("Model JSON payload is not an object")
    return parsed


def _extract_required_skills(requirements: str) -> list[str]:
    explicit = re.search(r"required\s+skills\s*:\s*(.+)", requirements, re.IGNORECASE)
    if explicit:
        raw = explicit.group(1)
        tokens = [t.strip() for t in re.split(r"[,;|]", raw) if t.strip()]
        return _dedupe_preserve_order(tokens)

    # Fallback for free-form text: keep likely technical terms.
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9+#.\-]{1,}", requirements)
    blacklist = {"minimum", "years", "experience", "required", "skills", "and", "with", "of", "the"}
    skills = [token for token in tokens if token.lower() not in blacklist and not token.isdigit()]
    return _dedupe_preserve_order(skills)


def _extract_required_years(requirements: str) -> float:
    match = re.search(r"(\d+(?:\.\d+)?)\s*\+?\s*years?", requirements, re.IGNORECASE)
    return _to_float(match.group(1)) if match else 0.0


def _extract_candidate_years(cv_text: str) -> float:
    candidates = [
        _to_float(number) for number in re.findall(r"(\d+(?:\.\d+)?)\s*\+?\s*years?", cv_text, flags=re.IGNORECASE)
    ]
    return max(candidates, default=0.0)


def _normalize_skill_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _clamp_score(score: Any) -> int:
    try:
        value = round(float(score))
    except (TypeError, ValueError):
        return 0
    return max(0, min(100, value))
