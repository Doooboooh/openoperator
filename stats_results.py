#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_RESULT_DIR = SCRIPT_DIR / "result"
DEFAULT_PROBLEMS_JSON = SCRIPT_DIR / "problems.json"
DEFAULT_OUTPUT_JSON = SCRIPT_DIR / "result_stats.json"


@dataclass
class ProblemStats:
    problem_id: str
    problem_name: str
    best_score: float
    best_latency: float | None
    best_user: str
    best_github: str
    submission_count: int
    unique_user_count: int
    unique_repo_count: int
    avg_score: float
    median_score: float
    min_score: float
    max_score: float
    score_range: float
    difficulty: str | None
    category: str | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="统计 openoperator 比赛成绩数据")
    parser.add_argument("--result-dir", default=str(DEFAULT_RESULT_DIR), help="result 目录路径")
    parser.add_argument("--problems-json", default=str(DEFAULT_PROBLEMS_JSON), help="problems.json 路径")
    parser.add_argument("--start", type=int, default=1, help="起始题号，默认 1")
    parser.add_argument("--end", type=int, default=139, help="结束题号，默认 139")
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON), help="统计结果 JSON 输出路径")
    return parser.parse_args()


def normalize_problem_id(problem_id: int) -> str:
    return f"{problem_id:03d}"


def load_problem_meta(problems_json_path: Path) -> dict[str, dict]:
    if not problems_json_path.exists():
        return {}

    payload = json.loads(problems_json_path.read_text(encoding="utf-8"))
    tasks = payload.get("tasks", [])
    meta = {}
    for task in tasks:
        task_id = str(task.get("id", "")).zfill(3)
        meta[task_id] = {
            "name": task.get("name", task_id),
            "difficulty": task.get("description", {}).get("difficulty"),
            "category": task.get("description", {}).get("category"),
        }
    return meta


def load_result_file(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def safe_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def compute_problem_stats(problem_id: str, payload: dict, meta: dict[str, dict]) -> ProblemStats | None:
    results = payload.get("results", [])
    if not isinstance(results, list) or not results:
        return None

    scored_results = []
    for entry in results:
        if not isinstance(entry, dict):
            continue
        score = safe_float(entry.get("score"))
        if score is None or math.isnan(score):
            continue
        scored_results.append((entry, score))

    if not scored_results:
        return None

    scored_results.sort(key=lambda item: item[1], reverse=True)
    best_entry, best_score = scored_results[0]
    scores = [score for _, score in scored_results]
    users = {str(entry.get("user", "")).strip() for entry, _ in scored_results if str(entry.get("user", "")).strip()}
    repos = {str(entry.get("github", "")).strip() for entry, _ in scored_results if str(entry.get("github", "")).strip()}
    task_meta = meta.get(problem_id, {})

    return ProblemStats(
        problem_id=problem_id,
        problem_name=str(payload.get("problem_name") or task_meta.get("name") or problem_id),
        best_score=best_score,
        best_latency=safe_float(best_entry.get("latency")),
        best_user=str(best_entry.get("user", "")),
        best_github=str(best_entry.get("github", "")),
        submission_count=len(scored_results),
        unique_user_count=len(users),
        unique_repo_count=len(repos),
        avg_score=statistics.fmean(scores),
        median_score=statistics.median(scores),
        min_score=min(scores),
        max_score=max(scores),
        score_range=max(scores) - min(scores),
        difficulty=task_meta.get("difficulty"),
        category=task_meta.get("category"),
    )


def summarize_best_scores(problem_stats: list[ProblemStats]) -> dict:
    best_scores = [item.best_score for item in problem_stats]
    if not best_scores:
        return {}

    hardest_by_best = min(problem_stats, key=lambda item: item.best_score)
    easiest_by_best = max(problem_stats, key=lambda item: item.best_score)

    return {
        "count": len(best_scores),
        "min": min(best_scores),
        "max": max(best_scores),
        "mean": statistics.fmean(best_scores),
        "median": statistics.median(best_scores),
        "pstdev": statistics.pstdev(best_scores) if len(best_scores) > 1 else 0.0,
        "best_problem": {
            "problem_id": easiest_by_best.problem_id,
            "problem_name": easiest_by_best.problem_name,
            "best_score": easiest_by_best.best_score,
            "difficulty": easiest_by_best.difficulty,
            "category": easiest_by_best.category,
        },
        "worst_problem": {
            "problem_id": hardest_by_best.problem_id,
            "problem_name": hardest_by_best.problem_name,
            "best_score": hardest_by_best.best_score,
            "difficulty": hardest_by_best.difficulty,
            "category": hardest_by_best.category,
        },
        "top_10_best_problems": [
            {
                "problem_id": item.problem_id,
                "problem_name": item.problem_name,
                "best_score": item.best_score,
                "difficulty": item.difficulty,
                "category": item.category,
            }
            for item in sorted(problem_stats, key=lambda item: item.best_score, reverse=True)[:10]
        ],
        "top_10_worst_problems": [
            {
                "problem_id": item.problem_id,
                "problem_name": item.problem_name,
                "best_score": item.best_score,
                "difficulty": item.difficulty,
                "category": item.category,
            }
            for item in sorted(problem_stats, key=lambda item: item.best_score)[:10]
        ],
        "histogram_bins": build_histogram(best_scores, bins=10),
    }


def build_histogram(values: list[float], bins: int) -> list[dict]:
    if not values:
        return []
    left = min(values)
    right = max(values)
    if left == right:
        return [{"start": left, "end": right, "count": len(values)}]

    width = (right - left) / bins
    buckets = [0 for _ in range(bins)]
    for value in values:
        index = min(int((value - left) / width), bins - 1)
        buckets[index] += 1

    histogram = []
    for index, count in enumerate(buckets):
        bucket_start = left + index * width
        bucket_end = bucket_start + width
        histogram.append({
            "start": bucket_start,
            "end": bucket_end,
            "count": count,
        })
    return histogram


def summarize_activity(problem_stats: list[ProblemStats], missing_problem_ids: list[str]) -> dict:
    if not problem_stats:
        return {}

    most_submitted = max(problem_stats, key=lambda item: item.submission_count)
    least_submitted = min(problem_stats, key=lambda item: item.submission_count)
    most_competitive = max(problem_stats, key=lambda item: item.unique_repo_count)
    widest_spread = max(problem_stats, key=lambda item: item.score_range)

    return {
        "covered_problem_count": len(problem_stats),
        "missing_problem_count": len(missing_problem_ids),
        "missing_problem_ids": missing_problem_ids,
        "most_submitted_problem": {
            "problem_id": most_submitted.problem_id,
            "problem_name": most_submitted.problem_name,
            "submission_count": most_submitted.submission_count,
        },
        "least_submitted_problem": {
            "problem_id": least_submitted.problem_id,
            "problem_name": least_submitted.problem_name,
            "submission_count": least_submitted.submission_count,
        },
        "most_competitive_problem": {
            "problem_id": most_competitive.problem_id,
            "problem_name": most_competitive.problem_name,
            "unique_repo_count": most_competitive.unique_repo_count,
        },
        "widest_score_spread_problem": {
            "problem_id": widest_spread.problem_id,
            "problem_name": widest_spread.problem_name,
            "score_range": widest_spread.score_range,
        },
        "submission_count_histogram": build_histogram(
            [float(item.submission_count) for item in problem_stats],
            bins=10,
        ),
    }


def summarize_by_field(problem_stats: list[ProblemStats], field_name: str) -> dict[str, dict]:
    grouped: defaultdict[str, list[ProblemStats]] = defaultdict(list)
    for item in problem_stats:
        value = getattr(item, field_name) or "unknown"
        grouped[str(value)].append(item)

    summary = {}
    for key, items in sorted(grouped.items()):
        summary[key] = {
            "problem_count": len(items),
            "mean_best_score": statistics.fmean(item.best_score for item in items),
            "median_best_score": statistics.median(item.best_score for item in items),
            "mean_submission_count": statistics.fmean(item.submission_count for item in items),
            "mean_unique_repo_count": statistics.fmean(item.unique_repo_count for item in items),
        }
    return summary


def summarize_top_repos(result_payloads: list[dict]) -> dict:
    repo_best_count: Counter[str] = Counter()
    repo_submission_count: Counter[str] = Counter()
    repo_problem_coverage: defaultdict[str, set[str]] = defaultdict(set)

    for payload in result_payloads:
        problem_id = str(payload.get("problem_id", "")).zfill(3)
        results = payload.get("results", [])
        if not isinstance(results, list) or not results:
            continue

        best_entry = None
        best_score = None
        for entry in results:
            if not isinstance(entry, dict):
                continue
            score = safe_float(entry.get("score"))
            repo = str(entry.get("github", "")).strip()
            if not repo or score is None:
                continue
            repo_submission_count[repo] += 1
            repo_problem_coverage[repo].add(problem_id)
            if best_score is None or score > best_score:
                best_score = score
                best_entry = entry

        if best_entry is not None:
            repo = str(best_entry.get("github", "")).strip()
            if repo:
                repo_best_count[repo] += 1

    return {
        "top_repos_by_problem_wins": [
            {"github": repo, "problem_win_count": count}
            for repo, count in repo_best_count.most_common(15)
        ],
        "top_repos_by_total_submissions": [
            {"github": repo, "submission_count": count}
            for repo, count in repo_submission_count.most_common(15)
        ],
        "top_repos_by_problem_coverage": [
            {"github": repo, "covered_problem_count": len(problem_ids)}
            for repo, problem_ids in sorted(
                repo_problem_coverage.items(),
                key=lambda item: len(item[1]),
                reverse=True,
            )[:15]
        ],
    }


def print_summary(report: dict) -> None:
    score_dist = report["best_score_distribution"]
    activity = report["activity_summary"]

    print("=== 每题最好成绩分布 ===")
    print(
        f"已统计题目: {score_dist['count']} / {report['problem_range']['end'] - report['problem_range']['start'] + 1} "
        f"(缺失榜单: {activity['missing_problem_count']})"
    )
    print(
        f"最好成绩分布: min={score_dist['min']:.6f}, median={score_dist['median']:.6f}, "
        f"mean={score_dist['mean']:.6f}, max={score_dist['max']:.6f}, pstdev={score_dist['pstdev']:.6f}"
    )

    best_problem = score_dist["best_problem"]
    worst_problem = score_dist["worst_problem"]
    print(
        f"最好做题目(按榜首 score): #{best_problem['problem_id']} {best_problem['problem_name']} "
        f"score={best_problem['best_score']:.6f}"
    )
    print(
        f"最难题目(按榜首 score): #{worst_problem['problem_id']} {worst_problem['problem_name']} "
        f"score={worst_problem['best_score']:.6f}"
    )

    print("\n=== 其他有意思的统计 ===")
    print(
        f"提交最多题目: #{activity['most_submitted_problem']['problem_id']} "
        f"{activity['most_submitted_problem']['problem_name']} "
        f"({activity['most_submitted_problem']['submission_count']} 条)"
    )
    print(
        f"提交最少题目: #{activity['least_submitted_problem']['problem_id']} "
        f"{activity['least_submitted_problem']['problem_name']} "
        f"({activity['least_submitted_problem']['submission_count']} 条)"
    )
    print(
        f"参赛仓库最多题目: #{activity['most_competitive_problem']['problem_id']} "
        f"{activity['most_competitive_problem']['problem_name']} "
        f"({activity['most_competitive_problem']['unique_repo_count']} 个仓库)"
    )
    print(
        f"分差最大题目: #{activity['widest_score_spread_problem']['problem_id']} "
        f"{activity['widest_score_spread_problem']['problem_name']} "
        f"(score range={activity['widest_score_spread_problem']['score_range']:.6f})"
    )

    print("\nTop 5 夺榜仓库:")
    for item in report["top_repo_summary"]["top_repos_by_problem_wins"][:5]:
        print(f"  {item['github']}: {item['problem_win_count']} 题榜首")

    if activity["missing_problem_ids"]:
        print(f"\n无成绩题目: {', '.join(activity['missing_problem_ids'])}")


def main() -> None:
    args = parse_args()
    result_dir = Path(args.result_dir)
    problems_json_path = Path(args.problems_json)
    output_json_path = Path(args.output_json)
    meta = load_problem_meta(problems_json_path)

    problem_stats: list[ProblemStats] = []
    result_payloads: list[dict] = []
    missing_problem_ids: list[str] = []

    for problem_number in range(args.start, args.end + 1):
        problem_id = normalize_problem_id(problem_number)
        result_path = result_dir / f"{problem_id}.json"
        payload = load_result_file(result_path)
        if payload is None:
            missing_problem_ids.append(problem_id)
            continue

        payload["problem_id"] = str(payload.get("problem_id", problem_id)).zfill(3)
        result_payloads.append(payload)
        stats = compute_problem_stats(problem_id, payload, meta)
        if stats is not None:
            problem_stats.append(stats)

    report = {
        "problem_range": {"start": args.start, "end": args.end},
        "best_score_distribution": summarize_best_scores(problem_stats),
        "activity_summary": summarize_activity(problem_stats, missing_problem_ids),
        "difficulty_summary": summarize_by_field(problem_stats, "difficulty"),
        "category_summary": summarize_by_field(problem_stats, "category"),
        "top_repo_summary": summarize_top_repos(result_payloads),
        "per_problem": [
            {
                "problem_id": item.problem_id,
                "problem_name": item.problem_name,
                "best_score": item.best_score,
                "best_latency": item.best_latency,
                "best_user": item.best_user,
                "best_github": item.best_github,
                "submission_count": item.submission_count,
                "unique_user_count": item.unique_user_count,
                "unique_repo_count": item.unique_repo_count,
                "avg_score": item.avg_score,
                "median_score": item.median_score,
                "min_score": item.min_score,
                "max_score": item.max_score,
                "score_range": item.score_range,
                "difficulty": item.difficulty,
                "category": item.category,
            }
            for item in sorted(problem_stats, key=lambda item: item.problem_id)
        ],
    }

    output_json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print_summary(report)
    print(f"\n统计 JSON 已写入: {output_json_path}")


if __name__ == "__main__":
    main()

