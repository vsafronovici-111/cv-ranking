from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from cv_ranker.ollama_client import OllamaClient, OllamaConfig
from cv_ranker.ranker import CVRanker, RankConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cv-ranker",
        description="Rank candidate CVs against job requirements using local Ollama (qwen3:14b).",
    )
    parser.add_argument("--cv-folder", required=True, help="Folder with CV files (.txt, .md, .docx, .pdf).")
    parser.add_argument("--requirements", required=True, help="Job requirements text.")
    parser.add_argument("--model", default="qwen3:14b", help="Ollama model name.")
    parser.add_argument("--ollama-url", default="http://localhost:11434", help="Ollama base URL.")
    parser.add_argument(
        "--mode",
        choices=["auto", "llm", "heuristic"],
        default="auto",
        help="Scoring mode: auto uses LLM then fallback, llm only, or heuristic only.",
    )
    parser.add_argument("--timeout", type=int, default=90, help="Ollama timeout in seconds.")
    parser.add_argument("--top-k", type=int, default=0, help="Limit output to top K candidates; 0 shows all.")
    parser.add_argument("--output", choices=["text", "json"], default="text", help="Output format.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    client = None
    if args.mode in {"auto", "llm"}:
        client = OllamaClient(
            OllamaConfig(
                base_url=args.ollama_url,
                model=args.model,
                timeout_seconds=args.timeout,
            )
        )

    ranker = CVRanker(ollama_client=client)
    results = ranker.rank_folder(
        folder=Path(args.cv_folder),
        config=RankConfig(
            requirements=args.requirements,
            mode=args.mode,
            top_k=args.top_k,
        ),
    )

    if args.output == "json":
        payload = [
            {
                "filename": r.filename,
                "score": r.score,
                "matched_skills": r.matched_skills,
                "missing_skills": r.missing_skills,
                "years_experience": r.years_experience,
                "summary": r.summary,
                "warnings": r.warnings,
            }
            for r in results
        ]
        print(json.dumps(payload, indent=2))
        return 0

    _print_text_results(results)
    return 0


def _print_text_results(results: list) -> None:
    if not results:
        print("No supported CV files found.")
        return

    for index, result in enumerate(results, start=1):
        print(f"{index}. {result.filename}")
        print(f"   Score: {result.score}/100")
        print(f"   Matched: {', '.join(result.matched_skills) if result.matched_skills else '-'}")
        print(f"   Missing: {', '.join(result.missing_skills) if result.missing_skills else '-'}")
        print(f"   Years: {result.years_experience}")
        print(f"   Summary: {result.summary}")
        if result.warnings:
            print(f"   Warnings: {' | '.join(result.warnings)}")
        print()

