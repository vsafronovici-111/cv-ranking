from __future__ import annotations

import unittest
from pathlib import Path

from cv_ranker.ranker import CVRanker, RankConfig


class RankerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cv_folder = Path(__file__).parent / "fixtures" / "cvs"
        self.requirements = (
            "Minimum 5 years of experience, required skills: Java, Spring Boot, Kafka, PostgreSQL, MongoDB, Redis"
        )

    def test_heuristic_ranks_best_candidate_first(self) -> None:
        ranker = CVRanker(llm_client=None)
        results = ranker.rank_folder(
            folder=self.cv_folder,
            config=RankConfig(requirements=self.requirements, mode="heuristic"),
        )

        by_name = {item.filename: item for item in results}

        self.assertEqual(results[0].filename, "alice.txt")
        self.assertGreaterEqual(by_name["alice.txt"].score, 90)
        self.assertLessEqual(by_name["bob.txt"].score, 40)
        self.assertGreater(by_name["alice.txt"].score, by_name["bob.txt"].score)

    def test_no_matches_can_score_zero(self) -> None:
        ranker = CVRanker(llm_client=None)
        results = ranker.rank_folder(
            folder=self.cv_folder,
            config=RankConfig(requirements="required skills: Rust, Go, Kubernetes", mode="heuristic"),
        )

        bob = next(item for item in results if item.filename == "bob.txt")
        self.assertEqual(bob.score, 0)


if __name__ == "__main__":
    unittest.main()
