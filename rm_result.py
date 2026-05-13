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


def main():
    args = parse_args()
    score = parse_score(args.score)
    problem_id = normalize_problem_id(args.problem_id)
    on_or_before = parse_on_or_before(args.on_or_before)
    if args.github is None and args.user is None and score is None and on_or_before is None:
        raise SystemExit("至少提供 --github、--user、--score 或 --on-or-before 之一")

    result_dir = Path(args.result_dir)
    if not result_dir.is_dir():
        raise SystemExit(f"result 目录不存在: {result_dir}")

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
