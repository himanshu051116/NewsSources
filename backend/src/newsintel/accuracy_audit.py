from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from newsintel.adapters.extractors.article_html import extract_article_html
from newsintel.adapters.http.safe_fetcher import FetchRequest, SafeHttpFetcher
from newsintel.core.config import get_settings
from newsintel.domain.intelligence.extraction_fidelity import assess_extraction_fidelity


async def _audit(url: str) -> dict[str, object]:
    settings = get_settings()
    fetcher = SafeHttpFetcher(
        user_agent=settings.crawler_user_agent,
        timeout_seconds=settings.fetch_timeout_seconds,
        max_bytes=settings.fetch_max_bytes,
    )
    fetched = await fetcher.fetch(FetchRequest(url=url))
    if not 200 <= fetched.status_code < 300:
        return {
            "url": url,
            "final_url": fetched.final_url,
            "http_status": fetched.status_code,
            "ok": False,
            "error": "non_success_http_status",
        }
    article = extract_article_html(fetched.body, base_url=fetched.final_url)
    fidelity = assess_extraction_fidelity(
        fetched.body,
        base_url=fetched.final_url,
        article=article,
    )
    return {
        "url": url,
        "final_url": fetched.final_url,
        "http_status": fetched.status_code,
        "ok": bool(article.text_content),
        "headline": article.title,
        "canonical_url": article.canonical_url,
        "published_at": article.published_at.isoformat() if article.published_at else None,
        "modified_at": article.modified_at.isoformat() if article.modified_at else None,
        "byline": article.byline,
        "language": article.language,
        "word_count": article.word_count,
        "extraction_method": article.extraction_method,
        "warnings": list(article.warnings),
        "content_sha256": article.content_sha256,
        "raw_html_sha256": fetched.body_sha256,
        "fidelity": fidelity.to_dict(),
        "scope_note": (
            "Fidelity checks whether extraction agrees with signals in the publisher page; "
            "it does not determine whether the publisher's reporting is factually true."
        ),
    }


def _aggregate(results: list[dict[str, object]], *, min_fidelity: float) -> dict[str, object]:
    scores: list[float] = []
    labels: Counter[str] = Counter()
    discrepancies: Counter[str] = Counter()
    http_success = 0
    extraction_success = 0
    for result in results:
        status = result.get("http_status")
        if isinstance(status, int) and 200 <= status < 300:
            http_success += 1
        if result.get("ok"):
            extraction_success += 1
        fidelity = result.get("fidelity")
        if not isinstance(fidelity, dict):
            continue
        score = fidelity.get("score")
        if isinstance(score, int | float):
            scores.append(float(score))
        label = fidelity.get("label")
        if isinstance(label, str):
            labels[label] += 1
        for item in fidelity.get("discrepancies") or []:
            if isinstance(item, str):
                discrepancies[item] += 1
    measured = len(scores)
    passing = sum(score >= min_fidelity for score in scores)
    return {
        "url_count": len(results),
        "http_success_count": http_success,
        "extraction_success_count": extraction_success,
        "measurable_fidelity_count": measured,
        "measurable_fidelity_rate": round(measured / len(results), 6) if results else 0.0,
        "mean_fidelity_score": round(sum(scores) / measured, 6) if measured else None,
        "min_fidelity_score": round(min(scores), 6) if scores else None,
        "fidelity_pass_threshold": min_fidelity,
        "fidelity_pass_count": passing,
        "fidelity_pass_rate": round(passing / measured, 6) if measured else None,
        "labels": dict(labels),
        "top_discrepancies": [
            {"name": name, "count": count}
            for name, count in discrepancies.most_common(10)
        ],
        "scope": "publisher_page_extraction_fidelity_not_factual_truth",
    }


async def _main_async(args: argparse.Namespace) -> int:
    results: list[dict[str, object]] = []
    exit_code = 0
    for url in args.url:
        try:
            result = await _audit(url)
        except Exception as exc:  # noqa: BLE001 - CLI must report per-URL failures
            result = {
                "url": url,
                "ok": False,
                "error": type(exc).__name__,
                "message": str(exc),
            }
            exit_code = 2
        results.append(result)
        fidelity = result.get("fidelity")
        if isinstance(fidelity, dict):
            score = fidelity.get("score")
            if isinstance(score, int | float) and score < args.min_fidelity:
                exit_code = max(exit_code, 1)

    summary = _aggregate(results, min_fidelity=args.min_fidelity)
    if args.json:
        payload: object = {"summary": summary, "results": results} if args.summary else results
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        for result in results:
            print(f"\nURL: {result.get('url')}")
            if not result.get("ok"):
                print(f"  ERROR: {result.get('error')} {result.get('message', '')}".rstrip())
                continue
            print(f"  HTTP: {result.get('http_status')}  final={result.get('final_url')}")
            print(f"  Headline: {result.get('headline')}")
            print(f"  Published: {result.get('published_at')}")
            print(f"  Canonical: {result.get('canonical_url')}")
            print(
                f"  Extraction: {result.get('extraction_method')} · "
                f"{result.get('word_count')} words"
            )
            fidelity = result.get("fidelity")
            if isinstance(fidelity, dict):
                print(
                    f"  Publisher fidelity: {fidelity.get('label')} "
                    f"(score={fidelity.get('score')}, checks={fidelity.get('available_checks')})"
                )
                discrepancies = fidelity.get("discrepancies")
                if isinstance(discrepancies, list) and discrepancies:
                    print("  Discrepancies:")
                    for item in discrepancies:
                        print(f"    - {item}")
            warnings = result.get("warnings")
            if isinstance(warnings, list) and warnings:
                print("  Extraction warnings:")
                for item in warnings:
                    print(f"    - {item}")
        print("\nAggregate extraction audit:")
        print(
            f"  HTTP success: {summary['http_success_count']}/{summary['url_count']} · "
            f"extracted: {summary['extraction_success_count']}/{summary['url_count']}"
        )
        print(
            f"  Fidelity measured: {summary['measurable_fidelity_count']}/{summary['url_count']} · "
            f"mean={summary['mean_fidelity_score']} · pass rate={summary['fidelity_pass_rate']}"
        )
        print(
            "\nNote: publisher fidelity measures extraction consistency with the page, "
            "not factual truth of the reporting."
        )
    return exit_code


def run() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch live publisher pages and audit extraction fidelity without using the database."
    )
    parser.add_argument("--url", action="append", required=True, help="Public article URL; repeat for multiple pages.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    parser.add_argument(
        "--summary",
        action="store_true",
        help="With --json, emit aggregate extraction-fidelity metrics alongside per-URL results.",
    )
    parser.add_argument(
        "--min-fidelity",
        type=float,
        default=0.75,
        help="Return exit code 1 when a measurable fidelity score is below this threshold (default: 0.75).",
    )
    args = parser.parse_args()
    if not 0 <= args.min_fidelity <= 1:
        parser.error("--min-fidelity must be between 0 and 1")
    raise SystemExit(asyncio.run(_main_async(args)))


if __name__ == "__main__":
    run()
