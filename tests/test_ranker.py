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

        by_name = {item.filename: item for item in results}

        self.assertEqual(results[0].filename, "alice.txt")
        self.assertGreaterEqual(by_name["alice.txt"].score, 90)
        self.assertLessEqual(by_name["bob.txt"].score, 40)
        self.assertGreater(by_name["alice.txt"].score, by_name["bob.txt"].score)
        self.assertGreater(by_name["alice.txt"].score, by_name["derek.txt"].score)

    def test_no_matches_can_score_zero(self) -> None:
        ranker = CVRanker(ollama_client=None)
        results = ranker.rank_folder(
            folder=self.cv_folder,
            config=RankConfig(requirements="required skills: Rust, Go, Kubernetes", mode="heuristic"),
        )

        bob = next(item for item in results if item.filename == "bob.txt")
        self.assertEqual(bob.score, 0)

    def test_react_and_angular_requirement_favors_dual_skill_candidate(self) -> None:
        ranker = CVRanker(ollama_client=None)
        requirements = "required skills: React, Angular"
        results = ranker.rank_folder(
            folder=self.cv_folder,
            config=RankConfig(requirements=requirements, mode="heuristic"),
        )
        by_name = {item.filename: item for item in results}

        # Carla knows both React and Angular; Derek only knows React.
        self.assertEqual(by_name["carla.txt"].score, 80)
        self.assertGreater(by_name["carla.txt"].score, by_name["derek.txt"].score)
        self.assertIn("React", by_name["derek.txt"].matched_skills)
        self.assertIn("Angular", by_name["derek.txt"].missing_skills)

    def test_fullstack_java_react_requirement_ranks_elena_top(self) -> None:
        ranker = CVRanker(ollama_client=None)
        requirements = "required skills: Java, React"
        results = ranker.rank_folder(
            folder=self.cv_folder,
            config=RankConfig(requirements=requirements, mode="heuristic"),
        )
        by_name = {item.filename: item for item in results}

        # No years requirement stated, so a full skill match caps at 80.
        self.assertEqual(by_name["elena.txt"].score, 80)
        # Farhan has Java but Angular, not React.
        self.assertLess(by_name["farhan.txt"].score, by_name["elena.txt"].score)
        # Grace has React but Node.js, not Java.
        self.assertLess(by_name["grace.txt"].score, by_name["elena.txt"].score)

    def test_nodejs_react_requirement_ranks_grace_top(self) -> None:
        ranker = CVRanker(ollama_client=None)
        requirements = "required skills: Node.js, React"
        results = ranker.rank_folder(
            folder=self.cv_folder,
            config=RankConfig(requirements=requirements, mode="heuristic"),
        )
        by_name = {item.filename: item for item in results}

        self.assertEqual(by_name["grace.txt"].score, 80)
        self.assertLess(by_name["elena.txt"].score, by_name["grace.txt"].score)


if __name__ == "__main__":
    unittest.main()

