#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from decimal import Decimal, InvalidOperation
from datetime import datetime, time, timedelta, timezone
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_RESULT_DIR = SCRIPT_DIR / "result"
SCORE_TOLERANCE = Decimal("1e-5")
DATE_PARSE_TZ = timezone(timedelta(hours=8), name="Asia/Shanghai")


def parse_args():
    parser = argparse.ArgumentParser(
        description="删除 leaderboard/result 下符合条件的全部成绩"
    )
    parser.add_argument(
        "--result-dir",
        default=str(DEFAULT_RESULT_DIR),
        help="result 目录路径，默认 leaderboard/result",
    )
    parser.add_argument(
        "--github",
        default=None,
        help="按 github 仓库名精确删除，例如 foo/bar",
    )
    parser.add_argument(
        "--problem-id",
        default=None,
        help="仅处理指定题目号码，例如 1、001、138",
    )
    parser.add_argument(
        "--user",
        default=None,
        help="按榜单 user 名精确删除",
    )
    parser.add_argument(
        "--score",
        default=None,
        help="按 score 数值精确删除，例如 100.0",
    )
    parser.add_argument(
        "--on-or-before",
        default=None,
        help="按日期删除该日及之前的成绩，支持 5.18、5-18、2026-05-18、2026/05/18，按 Asia/Shanghai 解释",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只预览，不写回文件",
    )
    parser.add_argument(
        "--audit-report",
        default=None,
        help="按作弊审计脚本输出的 JSON 报告批量删除 findings 对应成绩",
    )
    return parser.parse_args()


def parse_score(score: str | None) -> Decimal | None:
    if score is None:
        return None
    try:
        return Decimal(score)
    except InvalidOperation as exc:
        raise SystemExit(f"无效的 --score 参数: {score}") from exc


def normalize_problem_id(problem_id: str | None) -> str | None:
    if problem_id is None:
        return None

    value = problem_id.strip()
    if not value:
        raise SystemExit("--problem-id 不能为空")
    if not value.isdigit():
        raise SystemExit(f"无效的 --problem-id 参数: {problem_id}，只能包含数字")
    return f"{int(value):03d}"


def score_matches(entry_score: object, score: Decimal | None) -> bool:
    if score is None:
        return True
    if not isinstance(entry_score, (int, float, str)):
        return False
    try:
        return abs(Decimal(str(entry_score)) - score) <= SCORE_TOLERANCE
    except InvalidOperation:
        return False


def parse_on_or_before(raw: str | None) -> datetime | None:
    if raw is None:
        return None

    value = raw.strip()
    if not value:
        raise SystemExit("--on-or-before 不能为空")

    normalized = value.replace("/", "-").replace(".", "-")
    parts = normalized.split("-")
    try:
        if len(parts) == 2:
            year = datetime.now(DATE_PARSE_TZ).year
            month, day = (int(part) for part in parts)
        elif len(parts) == 3:
            year, month, day = (int(part) for part in parts)
        else:
            raise ValueError
        cutoff_date = datetime(year, month, day, tzinfo=DATE_PARSE_TZ).date()
    except ValueError as exc:
        raise SystemExit(
            f"无效的 --on-or-before 参数: {raw}，支持 5.18、5-18、2026-05-18、2026/05/18"
        ) from exc

    return datetime.combine(cutoff_date, time.max, tzinfo=DATE_PARSE_TZ).astimezone(timezone.utc)


def timestamp_matches(entry_timestamp: object, on_or_before: datetime | None) -> bool:
    if on_or_before is None:
        return True
    if not isinstance(entry_timestamp, str):
        return False

    try:
        timestamp = datetime.fromisoformat(entry_timestamp)
    except ValueError:
        return False

    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc) <= on_or_before


def matches(
    entry: dict,
    github: str | None,
    user: str | None,
    score: Decimal | None,
    on_or_before: datetime | None,
) -> bool:
    if github is not None and entry.get("github") != github:
        return False
    if user is not None and entry.get("user") != user:
        return False
    if not score_matches(entry.get("score"), score):
        return False
    if not timestamp_matches(entry.get("timestamp"), on_or_before):
        return False
    return True


def exact_entry_matches(
    entry: dict,
    *,
    github: str | None,
    user: str | None,
    timestamp: str | None,
) -> bool:
    if github is not None and entry.get("github") != github:
        return False
    if user is not None and entry.get("user") != user:
        return False
    if timestamp is not None and entry.get("timestamp") != timestamp:
        return False
    return True


def rewrite_ranks(results: list[dict]):
    for idx, entry in enumerate(results, start=1):
        entry["rank"] = idx


def process_file(
    path: Path,
    github: str | None,
    user: str | None,
    score: Decimal | None,
    on_or_before: datetime | None,
    dry_run: bool,
) -> tuple[int, int]:
    data = json.loads(path.read_text(encoding="utf-8"))
    results = data.get("results", [])
    if not isinstance(results, list):
        raise ValueError(f"{path} 的 results 不是列表")

    kept = []
    removed = []
    for entry in results:
        if isinstance(entry, dict) and matches(entry, github, user, score, on_or_before):
            removed.append(entry)
        else:
            kept.append(entry)

    if not removed:
        return 0, len(results)

    rewrite_ranks(kept)
    data["results"] = kept
    data["last_updated"] = datetime.now(timezone.utc).isoformat()

    if not dry_run:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return len(removed), len(results)


def load_audit_findings(report_path: Path) -> list[dict]:
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit(f"无法解析审计报告 {report_path}: {exc}") from exc

    findings = payload.get("findings", [])
    if not isinstance(findings, list):
        raise SystemExit(f"审计报告 {report_path} 的 findings 不是列表")

    normalized = []
    for idx, item in enumerate(findings, start=1):
        if not isinstance(item, dict):
            raise SystemExit(f"审计报告第 {idx} 条 finding 不是对象")

        problem_id = normalize_problem_id(str(item.get("problem_id", "") or ""))
        github = item.get("repo_full_name")
        user = item.get("user")
        timestamp = item.get("timestamp")

        if not github or not user or not timestamp:
            raise SystemExit(
                f"审计报告第 {idx} 条 finding 缺少必要字段，需要至少包含 "
                f"problem_id/repo_full_name/user/timestamp"
            )

        normalized.append(
            {
                "problem_id": problem_id,
                "github": str(github),
                "user": str(user),
                "timestamp": str(timestamp),
                "source": item,
            }
        )

    return normalized


def process_audit_report(result_dir: Path, report_path: Path, dry_run: bool):
    findings = load_audit_findings(report_path)
    grouped: dict[str, list[dict]] = {}
    for finding in findings:
        grouped.setdefault(finding["problem_id"], []).append(finding)

    total_removed = 0
    touched_files = 0
    unmatched = []

    for problem_id, problem_findings in sorted(grouped.items()):
        path = result_dir / f"{problem_id}.json"
        if not path.exists():
            for finding in problem_findings:
                unmatched.append(
                    {
                        "problem_id": problem_id,
                        "github": finding["github"],
                        "user": finding["user"],
                        "timestamp": finding["timestamp"],
                        "reason": f"result file not found: {path}",
                    }
                )
            continue

        data = json.loads(path.read_text(encoding="utf-8"))
        results = data.get("results", [])
        if not isinstance(results, list):
            raise ValueError(f"{path} 的 results 不是列表")

        kept = []
        removed_count = 0
        remaining_targets = list(problem_findings)

        for entry in results:
            if not isinstance(entry, dict):
                kept.append(entry)
                continue

            matched_idx = next(
                (
                    idx
                    for idx, target in enumerate(remaining_targets)
                    if exact_entry_matches(
                        entry,
                        github=target["github"],
                        user=target["user"],
                        timestamp=target["timestamp"],
                    )
                ),
                None,
            )

            if matched_idx is None:
                kept.append(entry)
                continue

            removed_count += 1
            total_removed += 1
            remaining_targets.pop(matched_idx)

        if removed_count:
            rewrite_ranks(kept)
            data["results"] = kept
            data["last_updated"] = datetime.now(timezone.utc).isoformat()
            if not dry_run:
                path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            touched_files += 1
            print(f"{path.name}: removed {removed_count} / {len(results)} via audit report")

        for target in remaining_targets:
            unmatched.append(
                {
                    "problem_id": problem_id,
                    "github": target["github"],
                    "user": target["user"],
                    "timestamp": target["timestamp"],
                    "reason": "matching leaderboard entry not found",
                }
            )

    mode = "dry-run" if dry_run else "updated"
    print(
        f"{mode}: touched_files={touched_files}, removed_entries={total_removed}, "
        f"unmatched_findings={len(unmatched)}"
    )
    if unmatched:
        print("unmatched findings:")
        for item in unmatched:
            print(
                f"  problem={item['problem_id']} user={item['user']} "
                f"github={item['github']} timestamp={item['timestamp']} reason={item['reason']}"
            )


def main():
    args = parse_args()
    score = parse_score(args.score)
    problem_id = normalize_problem_id(args.problem_id)
    on_or_before = parse_on_or_before(args.on_or_before)
    if args.audit_report is None and args.github is None and args.user is None and score is None and on_or_before is None:
        raise SystemExit("至少提供 --github、--user、--score 或 --on-or-before 之一")

    result_dir = Path(args.result_dir)
    if not result_dir.is_dir():
        raise SystemExit(f"result 目录不存在: {result_dir}")

    if args.audit_report is not None:
        if any(value is not None for value in (args.github, args.user, args.score, args.on_or_before, args.problem_id)):
            raise SystemExit("--audit-report 模式下不要同时传 --github/--user/--score/--on-or-before/--problem-id")
        report_path = Path(args.audit_report)
        if not report_path.is_file():
            raise SystemExit(f"审计报告不存在: {report_path}")
        process_audit_report(result_dir, report_path, args.dry_run)
        return

    total_removed = 0
    touched_files = 0

    paths = sorted(result_dir.glob("*.json"))
    if problem_id is not None:
        paths = [path for path in paths if path.stem == problem_id]
        if not paths:
            raise SystemExit(f"未找到题目 {problem_id} 对应的结果文件")

    for path in paths:
        removed, total_before = process_file(
            path,
            args.github,
            args.user,
            score,
            on_or_before,
            args.dry_run,
        )
        if removed:
            touched_files += 1
            total_removed += removed
            print(f"{path.name}: removed {removed} / {total_before}")

    mode = "dry-run" if args.dry_run else "updated"
    print(f"{mode}: touched_files={touched_files}, removed_entries={total_removed}")


if __name__ == "__main__":
    main()

