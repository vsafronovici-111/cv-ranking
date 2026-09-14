from __future__ import annotations

from pathlib import Path

from cv_ranker.ranker import CVRanker, RankConfig

if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parent.parent
    cv_folder = repo_root / "tests" / "fixtures" / "cvs"
    requirements = (
        "Minimum 5 years of experience, required skills: Java, Spring Boot, Kafka, PostgreSQL, MongoDB, Redis"
    )

    ranker = CVRanker(llm_client=None)
    results = ranker.rank_folder(cv_folder, RankConfig(requirements=requirements, mode="heuristic"))

    for result in results:
        print(f"{result.filename}: {result.score}/100")
