from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

from finance_insight.config import Settings, settings
from finance_insight.schemas import ToolResult


class ChartGenerationTool:
    name = "chart_generation"
    description = "将已验证时间序列生成 PNG 趋势图。"

    def __init__(self, config: Settings = settings):
        self.output_dir = config.artifact_dir

    @staticmethod
    def _font_family() -> str:
        candidates = (
            "Noto Sans CJK SC", "Noto Sans CJK JP", "Microsoft YaHei",
            "SimHei", "WenQuanYi Zen Hei", "DejaVu Sans",
        )
        available = {font.name for font in font_manager.fontManager.ttflist}
        return next((name for name in candidates if name in available), "DejaVu Sans")

    def run(self, series: list[dict[str, Any]], *, trace_id: str) -> ToolResult:
        started = time.perf_counter()
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            paths: list[str] = []
            plt.rcParams["font.sans-serif"] = [self._font_family()]
            plt.rcParams["axes.unicode_minus"] = False
            for item in series:
                years = [point["year"] for point in item["points"]]
                values = [point["value"] for point in item["points"]]
                fig, ax = plt.subplots(figsize=(7, 4))
                ax.plot(years, values, marker="o", linewidth=2, color="#176b4d")
                ax.set_title(f"{item['company_name']} · {item['metric_name']}")
                ax.set_xlabel("报告年度")
                ax.set_ylabel(item["points"][0]["unit"])
                ax.grid(alpha=0.2)
                ax.set_xticks(years)
                fig.tight_layout()
                target = self.output_dir / (
                    f"{trace_id}_{item['stock_code']}_"
                    f"{re.sub(r'[^A-Za-z0-9_-]', '_', item['metric_code'])}.png"
                )
                fig.savefig(target, dpi=140, facecolor="#ffffff")
                plt.close(fig)
                paths.append(str(target.resolve()))
            return ToolResult(
                tool_name=self.name,
                status="success",
                data={"chart_paths": paths, "count": len(paths)},
                latency_ms=(time.perf_counter() - started) * 1000,
            )
        except Exception as exc:
            return ToolResult(
                tool_name=self.name,
                status="error",
                error=str(exc),
                latency_ms=(time.perf_counter() - started) * 1000,
            )
