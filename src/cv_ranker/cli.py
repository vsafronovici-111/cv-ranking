from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Sequence

from cv_ranker.config import load_db_settings, load_llm_settings
from cv_ranker.db import CVStore, DBSettings, FAILED, PENDING
from cv_ranker.llm_client import LLMClient, LLMClientConfig
from cv_ranker.parsing import iter_cv_files, parse_cv_bytes
from cv_ranker.ranker import CandidateScore, CVRanker, RankConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cv-ranker",
        description=(
            "Ingest, score, and rank candidate CVs against job requirements using "
            "an OpenAI-compatible LLM server (Ollama locally, vLLM in production), "
            "with a Postgres-backed durable processing queue."
        ),
    )
    parser.add_argument(
        "--env",
        choices=["local", "prod"],
        default=None,
        help="Environment profile to use (default: local, or $CV_RANKER_ENV). "
        "'local' targets Ollama, 'prod' targets vLLM.",
    )
    parser.add_argument("--dsn", default=None, help="Override the Postgres DSN (postgresql://user:pass@host/db).")

    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subparsers.add_parser("ingest", help="Load CV files from a folder into the database as PENDING.")
    ingest_parser.add_argument("--cv-folder", required=True, help="Folder with CV files (.txt, .md, .docx, .pdf).")

    process_parser = subparsers.add_parser(
        "process", help="Score PENDING/FAILED CVs from the database until the queue is empty."
    )
    process_parser.add_argument("--requirements", required=True, help="Job requirements text.")
    process_parser.add_argument("--model", default=None, help="Override the model name from the environment profile.")
    process_parser.add_argument(
        "--base-url", default=None, help="Override the OpenAI-compatible base URL (Ollama or vLLM)."
    )
    process_parser.add_argument("--api-key", default=None, help="Override the API key/token for the LLM server.")
    process_parser.add_argument("--timeout", type=int, default=None, help="Override request timeout in seconds.")
    process_parser.add_argument(
        "--mode",
        choices=["auto", "llm", "heuristic"],
        default="auto",
        help="Scoring mode: auto uses LLM then fallback, llm only, or heuristic only.",
    )
    process_parser.add_argument(
        "--only-failed", action="store_true", help="Only retry CVs currently in FAILED status (skip PENDING)."
    )

    report_parser = subparsers.add_parser("report", help="Print ranked results for SUCCEEDED CVs.")
    report_parser.add_argument("--top-k", type=int, default=0, help="Limit output to top K candidates; 0 shows all.")
    report_parser.add_argument("--output", choices=["text", "json"], default="text", help="Output format.")

    status_parser = subparsers.add_parser("status", help="Show CV counts grouped by processing status.")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    db_settings = load_db_settings(args.env)
    dsn = args.dsn or db_settings.dsn
    store = CVStore(DBSettings(dsn=dsn))
    store.init_schema()

    if args.command == "ingest":
        return _run_ingest(store, args)
    if args.command == "process":
        return _run_process(store, args)
    if args.command == "report":
        return _run_report(store, args)
    if args.command == "status":
        return _run_status(store)

    return 1


def _run_ingest(store: CVStore, args: argparse.Namespace) -> int:
    folder = Path(args.cv_folder)
    if not folder.exists() or not folder.is_dir():
        print(f"CV folder does not exist or is not a folder: {folder}")
        return 1

    inserted = 0
    skipped = 0
    for file_path in iter_cv_files(folder):
        added = store.ingest_file(file_path.name, file_path.read_bytes())
        if added:
            inserted += 1
        else:
            skipped += 1

    print(f"Ingested {inserted} new CV(s), skipped {skipped} duplicate(s).")
    return 0


def _run_process(store: CVStore, args: argparse.Namespace) -> int:
    client = None
    if args.mode in {"auto", "llm"}:
        settings = load_llm_settings(args.env)
        client = LLMClient(
            LLMClientConfig(
                base_url=args.base_url or settings.base_url,
                api_key=args.api_key or settings.api_key,
                model=args.model or settings.model,
                timeout_seconds=args.timeout or settings.timeout_seconds,
            )
        )

    ranker = CVRanker(llm_client=client)
    config = RankConfig(requirements=args.requirements, mode=args.mode)
    statuses = (FAILED,) if args.only_failed else (PENDING, FAILED)

    processed = 0
    succeeded = 0
    failed = 0
    while True:
        row = store.claim_next(statuses=statuses)
        if row is None:
            break

        processed += 1
        try:
            parsed = parse_cv_bytes(row["cv_file_name"], row["data"])
            score = ranker._score_candidate(parsed, config)
            store.mark_succeeded(row["id"], asdict(score))
            succeeded += 1
        except Exception as exc:  # noqa: BLE001 - persist any failure and keep going
            store.mark_failed(row["id"], str(exc))
            failed += 1

    print(f"Processed {processed} CV(s): {succeeded} succeeded, {failed} failed.")
    return 0


def _run_report(store: CVStore, args: argparse.Namespace) -> int:
    rows = store.fetch_all_succeeded()
    results = [
        CandidateScore(
            filename=row["cv_file_name"],
            score=row["score_json"].get("score", 0),
            matched_skills=row["score_json"].get("matched_skills", []),
            missing_skills=row["score_json"].get("missing_skills", []),
            years_experience=row["score_json"].get("years_experience", 0.0),
            summary=row["score_json"].get("summary", ""),
            warnings=row["score_json"].get("warnings", []),
        )
        for row in rows
    ]
    results.sort(key=lambda c: (-c.score, c.filename.lower()))

    if args.top_k > 0:
        results = results[: args.top_k]

    if args.output == "json":
        payload = [asdict(r) for r in results]
        print(json.dumps(payload, indent=2))
        return 0

    _print_text_results(results)
    return 0


def _run_status(store: CVStore) -> int:
    counts = store.counts_by_status()
    if not counts:
        print("No CVs in database yet.")
        return 0
    for status, count in sorted(counts.items()):
        print(f"{status}: {count}")
    return 0


def _print_text_results(results: list[CandidateScore]) -> None:
    if not results:
        print("No succeeded CVs found. Run 'ingest' then 'process' first.")
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



