from __future__ import annotations

from pathlib import Path
import unittest

from cv_ranker.ranker import CVRanker, RankConfig


class RankerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cv_folder = Path(__file__).parent / "fixtures" / "cvs"
        self.requirements = (
            "Minimum 5 years of experience, required skills: "
            "Java, Spring Boot, Kafka, PostgreSQL, MongoDB, Redis"
        )

    def test_heuristic_ranks_best_candidate_first(self) -> None:
        ranker = CVRanker(ollama_client=None)
        results = ranker.rank_folder(
            folder=self.cv_folder,
            config=RankConfig(requirements=self.requirements, mode="heuristic"),
        )

        self.assertEqual(results[0].filename, "alice.txt")
        self.assertGreater(results[0].score, results[1].score)
        self.assertGreaterEqual(results[0].score, 90)
        self.assertLessEqual(results[1].score, 40)

    def test_no_matches_can_score_zero(self) -> None:
        ranker = CVRanker(ollama_client=None)
        results = ranker.rank_folder(
            folder=self.cv_folder,
            config=RankConfig(requirements="required skills: Rust, Go, Kubernetes", mode="heuristic"),
        )

        bob = next(item for item in results if item.filename == "bob.txt")
        self.assertEqual(bob.score, 0)


if __name__ == "__main__":
    unittest.main()

