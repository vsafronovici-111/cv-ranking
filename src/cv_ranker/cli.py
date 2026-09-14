from __future__ import annotations

import argparse
import json
import uuid
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

from cv_ranker.config import load_db_settings, load_embedding_settings, load_llm_settings, load_qdrant_settings
from cv_ranker.cv_structurer import extract_cv_structure
from cv_ranker.db import FAILED, PENDING, CVStore, DBSettings
from cv_ranker.embedding_client import EmbeddingClient, EmbeddingClientConfig, EmbeddingClientError
from cv_ranker.llm_client import LLMClient, LLMClientConfig, LLMClientError
from cv_ranker.parsing import iter_cv_files, parse_cv_bytes
from cv_ranker.qdrant_store import CVVectorStore, CVVectorStoreError, QdrantSettings
from cv_ranker.ranker import CandidateScore, CVRanker, RankConfig

CV_CHUNK_ID_NAMESPACE = uuid.UUID("2f3b6f1a-6c3e-4a86-9f0b-2f7f6f3c6d21")


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
    ingest_parser.add_argument(
        "--no-embeddings",
        action="store_true",
        help="Skip generating/storing embeddings in Qdrant for newly ingested CVs.",
    )

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

    subparsers.add_parser("status", help="Show CV counts grouped by processing status.")

    find_parser = subparsers.add_parser("find", help="Embed a criteria text and search Qdrant for similar CVs.")
    find_parser.add_argument("--criteria", required=True, help="Free-text requirements to embed and search against.")
    find_parser.add_argument("--top-k", type=int, default=10, help="Number of results to return.")
    find_parser.add_argument("--output", choices=["text", "json"], default="text", help="Output format.")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "find":
        return _run_find(args)

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

    llm_client = None
    embedder = None
    vector_store = None
    if not args.no_embeddings:
        llm_settings = load_llm_settings(args.env)
        embedding_settings = load_embedding_settings(args.env)
        qdrant_settings = load_qdrant_settings(args.env)
        llm_client = LLMClient(
            LLMClientConfig(
                base_url=llm_settings.base_url,
                api_key=llm_settings.api_key,
                model=llm_settings.model,
                timeout_seconds=llm_settings.timeout_seconds,
            )
        )
        embedder = EmbeddingClient(
            EmbeddingClientConfig(
                base_url=embedding_settings.base_url,
                api_key=embedding_settings.api_key,
                model=embedding_settings.model,
                timeout_seconds=embedding_settings.timeout_seconds,
            )
        )
        vector_store = CVVectorStore(QdrantSettings(url=qdrant_settings.url, api_key=qdrant_settings.api_key))

    inserted = 0
    skipped = 0
    embedded = 0
    embedding_failures = 0
    collection_ready = False

    for file_path in iter_cv_files(folder):
        data = file_path.read_bytes()
        cv_id = store.ingest_file(file_path.name, data)
        if cv_id is None:
            skipped += 1
            continue

        inserted += 1

        if llm_client is None or embedder is None or vector_store is None:
            continue

        try:
            parsed = parse_cv_bytes(file_path.name, data)
            text = parsed.text.strip()
            if not text:
                print(f"  [{file_path.name}] no extractable text, skipping embedding.")
                continue

            structure = extract_cv_structure(llm_client, text)
            chunks = {
                "summary": structure.summary,
                "technologies": ", ".join(structure.technologies),
                "experience": structure.experience,
            }

            print(chunks)

            stored_chunks = 0
            for chunk_type, chunk_text in chunks.items():
                if not chunk_text:
                    continue

                vector = embedder.embed(chunk_text)
                if not collection_ready:
                    vector_store.ensure_collection(vector_size=len(vector))
                    collection_ready = True

                point_id = str(uuid.uuid5(CV_CHUNK_ID_NAMESPACE, f"{cv_id}:{chunk_type}"))
                vector_store.upsert_cv_embedding(
                    point_id=point_id,
                    vector=vector,
                    payload={"cv_id": cv_id, "cv_file_name": file_path.name, "chunk_type": chunk_type},
                )
                stored_chunks += 1

            if stored_chunks > 0:
                embedded += 1
            else:
                print(f"  [{file_path.name}] LLM extracted no usable chunks, skipping embedding.")
        except (LLMClientError, EmbeddingClientError, CVVectorStoreError) as exc:
            embedding_failures += 1
            print(f"  [{file_path.name}] embedding failed: {exc}")

    print(f"Ingested {inserted} new CV(s), skipped {skipped} duplicate(s).")
    if embedder is not None:
        print(f"Embeddings: {embedded} CV(s) chunked and stored, {embedding_failures} failed.")
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
            score = ranker.score_candidate(parsed, config)
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


def _run_find(args: argparse.Namespace) -> int:
    embedding_settings = load_embedding_settings(args.env)
    qdrant_settings = load_qdrant_settings(args.env)

    embedder = EmbeddingClient(
        EmbeddingClientConfig(
            base_url=embedding_settings.base_url,
            api_key=embedding_settings.api_key,
            model=embedding_settings.model,
            timeout_seconds=embedding_settings.timeout_seconds,
        )
    )
    vector_store = CVVectorStore(QdrantSettings(url=qdrant_settings.url, api_key=qdrant_settings.api_key))

    try:
        vector = embedder.embed(args.criteria)
        matches = vector_store.search_similar(vector, top_k=args.top_k)
    except (EmbeddingClientError, CVVectorStoreError) as exc:
        print(f"Search failed: {exc}")
        return 1

    if args.output == "json":
        payload = [
            {
                "score": match["score"],
                "cv_id": match["payload"].get("cv_id"),
                "cv_file_name": match["payload"].get("cv_file_name"),
                "chunk_type": match["payload"].get("chunk_type"),
            }
            for match in matches
        ]
        print(json.dumps(payload, indent=2))
        return 0

    if not matches:
        print("No matching CVs found. Run 'ingest' first to populate embeddings.")
        return 0

    for index, match in enumerate(matches, start=1):
        cv_id = match["payload"].get("cv_id")
        cv_file_name = match["payload"].get("cv_file_name")
        chunk_type = match["payload"].get("chunk_type", "?")
        print(f"{index}. {cv_file_name} (cv_id={cv_id}, chunk={chunk_type}, score={match['score']:.4f})")
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
