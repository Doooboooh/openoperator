#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import json
from pathlib import Path

MPLCONFIG_DIR = Path("/tmp/matplotlib-openoperator")
MPLCONFIG_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(MPLCONFIG_DIR))

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT_JSON = SCRIPT_DIR / "result_stats.json"
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "figures"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="将 result_stats.json 绘制为论文风格图表")
    parser.add_argument("--input-json", default=str(DEFAULT_INPUT_JSON), help="统计 JSON 路径")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="图片输出目录")
    parser.add_argument(
        "--formats",
        nargs="+",
        default=["png", "pdf"],
        help="输出格式，例如 png pdf svg",
    )
    return parser.parse_args()


def setup_style() -> None:
    sns.set_theme(style="whitegrid", context="paper")
    plt.rcParams.update({
        "figure.dpi": 180,
        "savefig.dpi": 300,
        "font.size": 10,
        "axes.titlesize": 12,
        "axes.labelsize": 10,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
        "legend.fontsize": 9,
        "figure.titlesize": 13,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.edgecolor": "#333333",
        "grid.color": "#D9D9D9",
        "grid.linewidth": 0.7,
        "grid.alpha": 0.7,
        "lines.linewidth": 1.6,
        "patch.edgecolor": "#333333",
        "patch.linewidth": 0.6,
        "font.family": "DejaVu Sans",
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })


def load_stats(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def save_figure(fig: plt.Figure, output_dir: Path, name: str, formats: list[str]) -> None:
    for fmt in formats:
        fig.savefig(output_dir / f"{name}.{fmt}", bbox_inches="tight")
    plt.close(fig)


def annotate_panel(ax: plt.Axes, label: str) -> None:
    ax.text(
        -0.12,
        1.04,
        label,
        transform=ax.transAxes,
        fontsize=12,
        fontweight="bold",
        va="bottom",
        ha="left",
    )


def plot_best_score_distribution(stats: dict, output_dir: Path, formats: list[str]) -> None:
    per_problem = stats["per_problem"]
    scores = np.array([item["best_score"] for item in per_problem], dtype=float)
    bins = max(12, min(24, int(np.sqrt(len(scores)) * 2))) if len(scores) else 12

    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.1), gridspec_kw={"width_ratios": [1.1, 1]})

    ax = axes[0]
    sns.histplot(scores, bins=bins, kde=True, color="#4C72B0", edgecolor="white", alpha=0.9, ax=ax)
    ax.set_xlabel("Best score per problem")
    ax.set_ylabel("Problem count")
    ax.set_title("Distribution of Best Scores")
    annotate_panel(ax, "A")

    summary = stats["best_score_distribution"]
    text = "\n".join([
        f"n = {summary['count']}",
        f"mean = {summary['mean']:.2f}",
        f"median = {summary['median']:.2f}",
        f"std = {summary['pstdev']:.2f}",
        f"min = {summary['min']:.2f}",
        f"max = {summary['max']:.2f}",
    ])
    ax.text(
        0.98,
        0.95,
        text,
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=8.5,
        bbox={"boxstyle": "round,pad=0.3", "facecolor": "white", "edgecolor": "#BBBBBB", "alpha": 0.95},
    )

    ax = axes[1]
    sorted_items = sorted(per_problem, key=lambda item: item["best_score"], reverse=True)
    top_items = sorted_items[:10]
    bottom_items = sorted(per_problem, key=lambda item: item["best_score"])[:10]
    combined = bottom_items + top_items
    labels = [f"{item['problem_id']}" for item in combined]
    values = [item["best_score"] for item in combined]
    colors = ["#C44E52"] * len(bottom_items) + ["#55A868"] * len(top_items)

    y = np.arange(len(combined))
    ax.barh(y, values, color=colors, alpha=0.9)
    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    ax.set_xlabel("Best score")
    ax.set_ylabel("Problem ID")
    ax.set_title("Lowest and Highest Scoring Problems")
    annotate_panel(ax, "B")

    for i, value in enumerate(values):
        ax.text(value, i, f" {value:.2f}", va="center", ha="left", fontsize=8)

    fig.suptitle("Problem-Level Best Score Statistics", y=1.03, fontweight="bold")
    fig.subplots_adjust(wspace=0.35)
    save_figure(fig, output_dir, "best_score_distribution", formats)


def plot_problem_activity(stats: dict, output_dir: Path, formats: list[str]) -> None:
    per_problem = stats["per_problem"]
    ids = [item["problem_id"] for item in per_problem]
    submissions = np.array([item["submission_count"] for item in per_problem], dtype=float)
    repos = np.array([item["unique_repo_count"] for item in per_problem], dtype=float)

    fig, axes = plt.subplots(2, 1, figsize=(11, 6.5), sharex=True, gridspec_kw={"hspace": 0.12})

    ax = axes[0]
    ax.plot(ids, submissions, color="#4C72B0", marker="o", markersize=2.8, linewidth=1.2)
    ax.fill_between(np.arange(len(ids)), submissions, color="#4C72B0", alpha=0.12)
    ax.set_ylabel("Submission count")
    ax.set_title("Problem Activity Across the Benchmark")
    annotate_panel(ax, "A")

    ax = axes[1]
    ax.plot(ids, repos, color="#55A868", marker="o", markersize=2.8, linewidth=1.2)
    ax.fill_between(np.arange(len(ids)), repos, color="#55A868", alpha=0.12)
    ax.set_ylabel("Unique repos")
    ax.set_xlabel("Problem ID")
    annotate_panel(ax, "B")

    tick_positions = np.linspace(0, len(ids) - 1, num=min(12, len(ids)), dtype=int)
    axes[1].set_xticks(tick_positions)
    axes[1].set_xticklabels([ids[i] for i in tick_positions], rotation=0)

    fig.subplots_adjust(hspace=0.18, left=0.08, right=0.98, top=0.93, bottom=0.1)
    save_figure(fig, output_dir, "problem_activity", formats)


def plot_difficulty_comparison(stats: dict, output_dir: Path, formats: list[str]) -> None:
    per_problem = stats["per_problem"]
    ordered = ["basic", "easy", "medium", "hard", "unknown"]
    grouped = {key: [] for key in ordered}
    for item in per_problem:
        difficulty = item.get("difficulty") or "unknown"
        if difficulty not in grouped:
            grouped[difficulty] = []
        grouped[difficulty].append(item["best_score"])

    labels = [key for key in ordered if grouped.get(key)]
    data = [grouped[key] for key in labels]
    palette = ["#8172B3", "#64B5CD", "#4C72B0", "#C44E52", "#8C8C8C"][:len(labels)]

    fig, ax = plt.subplots(figsize=(7.2, 4.5))
    box = ax.boxplot(
        data,
        patch_artist=True,
        tick_labels=labels,
        medianprops={"color": "#222222", "linewidth": 1.4},
        whiskerprops={"color": "#555555"},
        capprops={"color": "#555555"},
        flierprops={"marker": "o", "markerfacecolor": "#999999", "markersize": 3, "markeredgewidth": 0},
    )
    for patch, color in zip(box["boxes"], palette):
        patch.set_facecolor(color)
        patch.set_alpha(0.7)

    for i, values in enumerate(data, start=1):
        x = np.random.normal(i, 0.05, size=len(values))
        ax.scatter(x, values, s=10, color="#222222", alpha=0.35, linewidths=0)

    ax.set_ylabel("Best score per problem")
    ax.set_xlabel("Difficulty")
    ax.set_title("Best Score Distribution by Difficulty")
    ax.grid(axis="y", linestyle="--", alpha=0.45)
    save_figure(fig, output_dir, "difficulty_comparison", formats)


def plot_category_summary(stats: dict, output_dir: Path, formats: list[str]) -> None:
    category_summary = stats["category_summary"]
    rows = []
    for category, item in category_summary.items():
        rows.append((category, item["mean_best_score"], item["problem_count"]))

    rows.sort(key=lambda row: row[1], reverse=True)
    categories = [row[0] for row in rows[:12]]
    mean_scores = [row[1] for row in rows[:12]]
    counts = [row[2] for row in rows[:12]]

    fig, ax = plt.subplots(figsize=(9.5, 4.8))
    colors = sns.color_palette("Blues_r", n_colors=len(categories))
    y = np.arange(len(categories))
    bars = ax.barh(y, mean_scores, color=colors, alpha=0.95)
    ax.set_yticks(y)
    ax.set_yticklabels(categories)
    ax.invert_yaxis()
    ax.set_xlabel("Mean best score")
    ax.set_ylabel("Category")
    ax.set_title("Top Categories by Mean Best Score")

    for bar, score, count in zip(bars, mean_scores, counts):
        ax.text(
            bar.get_width(),
            bar.get_y() + bar.get_height() / 2,
            f" {score:.2f} (n={count})",
            va="center",
            ha="left",
            fontsize=8,
        )

    save_figure(fig, output_dir, "category_summary", formats)


def write_manifest(output_dir: Path, formats: list[str]) -> None:
    manifest = {
        "figures": [
            {
                "basename": "best_score_distribution",
                "description": "每题最好成绩的分布，以及最高/最低题目对比",
                "formats": formats,
            },
            {
                "basename": "problem_activity",
                "description": "各题提交量与唯一仓库数的变化趋势",
                "formats": formats,
            },
            {
                "basename": "difficulty_comparison",
                "description": "不同难度题目的最好成绩分布箱线图",
                "formats": formats,
            },
            {
                "basename": "category_summary",
                "description": "各类别题目的平均最好成绩比较",
                "formats": formats,
            },
        ]
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    args = parse_args()
    input_json = Path(args.input_json)
    output_dir = Path(args.output_dir)

    stats = load_stats(input_json)
    ensure_dir(output_dir)
    setup_style()

    plot_best_score_distribution(stats, output_dir, args.formats)
    plot_problem_activity(stats, output_dir, args.formats)
    plot_difficulty_comparison(stats, output_dir, args.formats)
    plot_category_summary(stats, output_dir, args.formats)
    write_manifest(output_dir, args.formats)

    print(f"图表已输出到: {output_dir}")
    for figure in sorted(output_dir.iterdir()):
        if figure.is_file():
            print(f" - {figure.name}")


if __name__ == "__main__":
    main()

