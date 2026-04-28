#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_RESULT_DIR = SCRIPT_DIR / "result"


def parse_args():
    parser = argparse.ArgumentParser(
        description="删除 leaderboard/result 下某个队伍的全部成绩"
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
        "--user",
        default=None,
        help="按榜单 user 名精确删除",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只预览，不写回文件",
    )
    return parser.parse_args()


def matches(entry: dict, github: str | None, user: str | None) -> bool:
    if github is not None and entry.get("github") != github:
        return False
    if user is not None and entry.get("user") != user:
        return False
    return True


def rewrite_ranks(results: list[dict]):
    for idx, entry in enumerate(results, start=1):
        entry["rank"] = idx


def process_file(path: Path, github: str | None, user: str | None, dry_run: bool) -> tuple[int, int]:
    data = json.loads(path.read_text(encoding="utf-8"))
    results = data.get("results", [])
    if not isinstance(results, list):
        raise ValueError(f"{path} 的 results 不是列表")

    kept = []
    removed = []
    for entry in results:
        if isinstance(entry, dict) and matches(entry, github, user):
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
    if args.github is None and args.user is None:
        raise SystemExit("至少提供 --github 或 --user 之一")

    result_dir = Path(args.result_dir)
    if not result_dir.is_dir():
        raise SystemExit(f"result 目录不存在: {result_dir}")

    total_removed = 0
    touched_files = 0

    for path in sorted(result_dir.glob("*.json")):
        removed, total_before = process_file(path, args.github, args.user, args.dry_run)
        if removed:
            touched_files += 1
            total_removed += removed
            print(f"{path.name}: removed {removed} / {total_before}")

    mode = "dry-run" if args.dry_run else "updated"
    print(f"{mode}: touched_files={touched_files}, removed_entries={total_removed}")


if __name__ == "__main__":
    main()

