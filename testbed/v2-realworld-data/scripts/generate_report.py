#!/usr/bin/env python3
"""
TotalReclaw v2.0 Real-World Data Evaluation Report Generator

Generates comprehensive evaluation reports comparing:
- Baselines: BM25, Vector-Only, OpenClaw-Hybrid, QMD-Hybrid
- TotalReclaw: v0.2, v0.5, v0.6

Output:
- reports/EVALUATION_REPORT.md (comprehensive technical)
- reports/EXECUTIVE_SUMMARY.html (for decision makers)
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass


# Paths
RESULTS_DIR = Path(__file__).parent.parent / "results"
REPORTS_DIR = Path(__file__).parent.parent / "reports"


@dataclass
class AlgorithmResult:
    """Normalized result data for an algorithm."""
    name: str
    precision_at_5: float = 0.0
    recall_at_5: float = 0.0
    f1_at_5: float = 0.0
    mrr: float = 0.0
    map_score: float = 0.0
    ndcg_at_5: float = 0.0
    latency_p50_ms: float = 0.0
    latency_p95_ms: float = 0.0
    latency_p99_ms: float = 0.0
    latency_mean_ms: float = 0.0
    queries_evaluated: int = 0


class V2ReportGenerator:
    """Generate v2.0 real-world data evaluation reports."""

    # Algorithms to compare
    ALGORITHMS = [
        "BM25-Only",
        "Vector-Only",
        "OpenClaw-Hybrid",
        "QMD-Hybrid",
        "TotalReclaw-v0.2",
        "TotalReclaw-v0.5",
        "TotalReclaw-v0.6",
    ]

    def __init__(self):
        self.results: Dict[str, AlgorithmResult] = {}

    def load_results(self) -> bool:
        """Load all result files from results directory."""

        print("Loading result files...")

        # Load baseline results
        for algo in ["bm25", "vector", "openclaw", "qmd"]:
            file_path = RESULTS_DIR / f"baselines_{algo}.json"
            if file_path.exists():
                try:
                    with open(file_path, 'r') as f:
                        data = json.load(f)
                        self._parse_baseline(data)
                        print(f"  Loaded {algo} baseline")
                except json.JSONDecodeError as e:
                    print(f"  Warning: Failed to parse {file_path}: {e}")

        # Load TotalReclaw results
        for version in ["v02", "v05", "v06"]:
            file_path = RESULTS_DIR / f"totalreclaw_{version}.json"
            if file_path.exists():
                try:
                    with open(file_path, 'r') as f:
                        data = json.load(f)
                        self._parse_totalreclaw(data, version)
                        print(f"  Loaded TotalReclaw {version}")
                except json.JSONDecodeError as e:
                    print(f"  Warning: Failed to parse {file_path}: {e}")

        return len(self.results) > 0

    def _parse_baseline(self, data: Dict[str, Any]):
        """Parse baseline result file."""

        name = data.get("algorithm_name", "Unknown")
        metrics = data.get("aggregate_metrics", {})
        latency = metrics.get("latency", {})

        result = AlgorithmResult(
            name=name,
            precision_at_5=metrics.get("precision_at_5", 0.0),
            recall_at_5=metrics.get("recall_at_5", 0.0),
            f1_at_5=metrics.get("f1_at_5", 0.0),
            mrr=metrics.get("mrr", 0.0),
            map_score=metrics.get("map", 0.0),
            ndcg_at_5=metrics.get("ndcg_at_5", 0.0),
            latency_p50_ms=latency.get("p50_ms", 0.0),
            latency_p95_ms=latency.get("p95_ms", 0.0),
            latency_p99_ms=latency.get("p99_ms", 0.0),
            latency_mean_ms=latency.get("mean_ms", 0.0),
            queries_evaluated=metrics.get("queries_evaluated", 0),
        )
        self.results[name] = result

    def _parse_totalreclaw(self, data: Dict[str, Any], version: str):
        """Parse TotalReclaw result file."""

        name = data.get("algorithm_name", f"TotalReclaw-{version}")
        metrics = data.get("aggregate_metrics", {})
        latency = metrics.get("latency", {})

        # Normalize version naming
        if version == "v02":
            name = "TotalReclaw-v0.2"
        elif version == "v05":
            name = "TotalReclaw-v0.5"
        elif version == "v06":
            name = "TotalReclaw-v0.6"

        result = AlgorithmResult(
            name=name,
            precision_at_5=metrics.get("precision_at_5", 0.0),
            recall_at_5=metrics.get("recall_at_5", 0.0),
            f1_at_5=metrics.get("f1_at_5", 0.0),
            mrr=metrics.get("mrr", 0.0),
            map_score=metrics.get("map", 0.0),
            ndcg_at_5=metrics.get("ndcg_at_5", 0.0),
            latency_p50_ms=latency.get("p50_ms", 0.0),
            latency_p95_ms=latency.get("p95_ms", 0.0),
            latency_p99_ms=latency.get("p99_ms", 0.0),
            latency_mean_ms=latency.get("mean_ms", 0.0),
            queries_evaluated=metrics.get("queries_evaluated", 0),
        )
        self.results[name] = result

    def get_sorted_results(self, by: str = "f1") -> List[AlgorithmResult]:
        """Get results sorted by metric."""
        reverse = by in ["f1", "precision", "recall", "mrr", "map", "ndcg"]
        key_map = {
            "f1": lambda x: x.f1_at_5,
            "precision": lambda x: x.precision_at_5,
            "recall": lambda x: x.recall_at_5,
            "mrr": lambda x: x.mrr,
            "map": lambda x: x.map_score,
            "ndcg": lambda x: x.ndcg_at_5,
            "latency": lambda x: x.latency_p50_ms,
        }
        return sorted(self.results.values(), key=key_map.get(by, lambda x: x.f1_at_5), reverse=reverse)

    def make_go_no_go_decision(self) -> Dict[str, Any]:
        """Make Go/No-Go decision based on v0.6 results."""

        v06 = self.results.get("TotalReclaw-v0.6")
        if not v06:
            return {"decision": "PENDING", "rationale": "No v0.6 results available"}

        # Best hybrid baselines
        openclaw = self.results.get("OpenClaw-Hybrid")
        qmd = self.results.get("QMD-Hybrid")

        best_baseline = None
        if openclaw and qmd:
            best_baseline = openclaw if openclaw.f1_at_5 >= qmd.f1_at_5 else qmd
        elif openclaw:
            best_baseline = openclaw
        elif qmd:
            best_baseline = qmd

        # Decision criteria
        f1_threshold = 0.20  # Minimum F1 for Go
        parity_threshold = 0.02  # Within 2% of baseline is parity
        latency_threshold_ms = 100  # Maximum acceptable latency

        decision = "PENDING"
        rationale = []
        warnings = []

        if best_baseline:
            f1_gap = v06.f1_at_5 - best_baseline.f1_at_5

            # Check F1 threshold
            if v06.f1_at_5 >= f1_threshold:
                rationale.append(f"F1@5 of {v06.f1_at_5:.3f} meets minimum threshold ({f1_threshold})")
            else:
                warnings.append(f"F1@5 of {v06.f1_at_5:.3f} below minimum threshold ({f1_threshold})")

            # Check parity with best baseline
            if abs(f1_gap) <= parity_threshold:
                rationale.append(f"Achieves parity with {best_baseline.name} (gap: {f1_gap:+.3f})")
            elif f1_gap > 0:
                rationale.append(f"Exceeds {best_baseline.name} by {f1_gap:+.3f} F1")
            else:
                warnings.append(f"Lags behind {best_baseline.name} by {f1_gap:.3f} F1")

        # Check latency
        if v06.latency_p50_ms <= latency_threshold_ms:
            rationale.append(f"Latency p50 of {v06.latency_p50_ms:.0f}ms is acceptable")
        else:
            warnings.append(f"Latency p50 of {v06.latency_p50_ms:.0f}ms exceeds threshold ({latency_threshold_ms}ms)")

        # Make decision
        if not warnings:
            decision = "GO"
        elif len(warnings) == 1:
            decision = "MODIFY"
        else:
            decision = "NO-GO"

        return {
            "decision": decision,
            "rationale": " | ".join(rationale),
            "warnings": warnings,
            "v06_f1": v06.f1_at_5,
            "baseline_f1": best_baseline.f1_at_5 if best_baseline else None,
            "latency_ok": v06.latency_p50_ms <= latency_threshold_ms,
        }

    def generate_reports(self):
        """Generate both markdown and HTML reports."""

        REPORTS_DIR.mkdir(parents=True, exist_ok=True)

        # Generate markdown report
        md_path = REPORTS_DIR / "EVALUATION_REPORT.md"
        with open(md_path, 'w') as f:
            self._write_markdown_report(f)
        print(f"Generated: {md_path}")

        # Generate HTML summary
        html_path = REPORTS_DIR / "EXECUTIVE_SUMMARY.html"
        self._write_html_summary(html_path)
        print(f"Generated: {html_path}")

        return md_path, html_path

    def _write_markdown_report(self, f):
        """Write comprehensive markdown report."""

        # Header
        f.write("# TotalReclaw v2.0 Real-World Data Evaluation Report\n\n")
        f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"**Testbed Version:** v2.0 Real-World WhatsApp Data\n\n")
        f.write("---\n\n")

        # Executive Summary
        self._write_executive_summary_md(f)

        # Algorithm Comparison
        self._write_algorithm_comparison_md(f)

        # Version Improvements
        self._write_version_improvements_md(f)

        # Parity Analysis
        self._write_parity_analysis_md(f)

        # E2EE Overhead
        self._write_e2ee_overhead_md(f)

        # Query Expansion Impact
        self._write_query_expansion_md(f)

        # Recommendations
        self._write_recommendations_md(f)

        # Appendix
        self._write_appendix_md(f)

    def _write_executive_summary_md(self, f):
        """Write executive summary section."""

        f.write("## Executive Summary\n\n")

        decision = self.make_go_no_go_decision()

        # Decision badge
        emoji = {"GO": "✅", "MODIFY": "⚠️", "NO-GO": "❌", "PENDING": "⏳"}
        f.write(f"### {emoji.get(decision['decision'], '')} Decision: {decision['decision']}\n\n")

        # Key findings
        f.write("### Key Findings\n\n")

        v06 = self.results.get("TotalReclaw-v0.6")
        v05 = self.results.get("TotalReclaw-v0.5")
        v02 = self.results.get("TotalReclaw-v0.2")
        openclaw = self.results.get("OpenClaw-Hybrid")
        qmd = self.results.get("QMD-Hybrid")

        if v06:
            f.write(f"- **TotalReclaw v0.6 F1@5:** {v06.f1_at_5:.3f}\n")
            f.write(f"- **MRR:** {v06.mrr:.3f}\n")
            f.write(f"- **Latency p50:** {v06.latency_p50_ms:.0f}ms\n\n")

        if v06 and v02:
            f1_improvement = ((v06.f1_at_5 - v02.f1_at_5) / v02.f1_at_5 * 100) if v02.f1_at_5 > 0 else 0
            f.write(f"### v0.6 vs v0.2 Improvement\n\n")
            f.write(f"- **F1@5:** {v02.f1_at_5:.3f} → {v06.f1_at_5:.3f} ({f1_improvement:+.1f}%)\n")
            f.write(f"- **MRR:** {v02.mrr:.3f} → {v06.mrr:.3f}\n\n")

        # Parity section
        if v06 and (openclaw or qmd):
            f.write("### Parity with Production Baselines\n\n")
            if openclaw:
                f1_gap = v06.f1_at_5 - openclaw.f1_at_5
                status = "✓" if f1_gap >= 0 else "✗"
                f.write(f"- {status} **OpenClaw-Hybrid:** {v06.f1_at_5:.3f} vs {openclaw.f1_at_5:.3f} ({f1_gap:+.3f})\n")
            if qmd:
                f1_gap = v06.f1_at_5 - qmd.f1_at_5
                status = "✓" if f1_gap >= 0 else "✗"
                f.write(f"- {status} **QMD-Hybrid:** {v06.f1_at_5:.3f} vs {qmd.f1_at_5:.3f} ({f1_gap:+.3f})\n")
            f.write("\n")

        # Decision rationale
        f.write("### Decision Rationale\n\n")
        f.write(f"{decision['rationale']}\n\n")

        if decision['warnings']:
            f.write("### Concerns\n\n")
            for warning in decision['warnings']:
                f.write(f"- ⚠️ {warning}\n")
            f.write("\n")

    def _write_algorithm_comparison_md(self, f):
        """Write algorithm comparison table."""

        f.write("## Algorithm Comparison\n\n")

        # Accuracy table
        f.write("### Accuracy Metrics (All 7 Algorithms)\n\n")
        f.write("| Rank | Algorithm | P@5 | R@5 | F1@5 | MRR | MAP | NDCG@5 |\n")
        f.write("|------|-----------|-----|-----|------|-----|-----|--------|\n")

        sorted_by_f1 = self.get_sorted_results("f1")
        for i, r in enumerate(sorted_by_f1, 1):
            medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, "")
            f.write(f"| {i} | {medal} {r.name} | {r.precision_at_5:.3f} | {r.recall_at_5:.3f} | ")
            f.write(f"**{r.f1_at_5:.3f}** | {r.mrr:.3f} | {r.map_score:.3f} | {r.ndcg_at_5:.3f} |\n")

        f.write("\n")

        # Latency table
        f.write("### Latency Comparison\n\n")
        f.write("| Algorithm | p50 (ms) | p95 (ms) | p99 (ms) | Mean (ms) |\n")
        f.write("|-----------|----------|----------|----------|----------|\n")

        sorted_by_latency = sorted(self.results.values(), key=lambda x: x.latency_p50_ms)
        for r in sorted_by_latency:
            f.write(f"| {r.name} | {r.latency_p50_ms:.1f} | {r.latency_p95_ms:.1f} | ")
            f.write(f"{r.latency_p99_ms:.1f} | {r.latency_mean_ms:.1f} |\n")

        f.write("\n")

    def _write_version_improvements_md(self, f):
        """Write version improvement analysis."""

        f.write("## TotalReclaw Version Evolution\n\n")

        v02 = self.results.get("TotalReclaw-v0.2")
        v05 = self.results.get("TotalReclaw-v0.5")
        v06 = self.results.get("TotalReclaw-v0.6")

        if v02 and v05 and v06:
            f.write("### Version Comparison\n\n")
            f.write("| Metric | v0.2 | v0.5 | v0.6 | v0.6 vs v0.2 | v0.6 vs v0.5 |\n")
            f.write("|--------|------|------|------|-------------|-------------|\n")

            metrics = [
                ("F1@5", "f1_at_5"),
                ("Precision@5", "precision_at_5"),
                ("Recall@5", "recall_at_5"),
                ("MRR", "mrr"),
                ("NDCG@5", "ndcg_at_5"),
            ]

            for label, attr in metrics:
                v02_val = getattr(v02, attr)
                v05_val = getattr(v05, attr)
                v06_val = getattr(v06, attr)

                v06_vs_v02 = ((v06_val - v02_val) / v02_val * 100) if v02_val > 0 else 0
                v06_vs_v05 = ((v06_val - v05_val) / v05_val * 100) if v05_val > 0 else 0

                f.write(f"| {label} | {v02_val:.3f} | {v05_val:.3f} | {v06_val:.3f} | ")
                f.write(f"{v06_vs_v02:+.1f}% | {v06_vs_v05:+.1f}% |\n")

            f.write("\n")

            # Latency comparison
            f.write("### Latency Evolution\n\n")
            f.write("| Version | p50 (ms) | p95 (ms) | p99 (ms) |\n")
            f.write("|---------|----------|----------|----------|\n")
            f.write(f"| v0.2 | {v02.latency_p50_ms:.1f} | {v02.latency_p95_ms:.1f} | {v02.latency_p99_ms:.1f} |\n")
            f.write(f"| v0.5 | {v05.latency_p50_ms:.1f} | {v05.latency_p95_ms:.1f} | {v05.latency_p99_ms:.1f} |\n")
            f.write(f"| v0.6 | {v06.latency_p50_ms:.1f} | {v06.latency_p95_ms:.1f} | {v06.latency_p99_ms:.1f} |\n")
            f.write("\n")

    def _write_parity_analysis_md(self, f):
        """Write parity analysis with production baselines."""

        f.write("## v0.6 vs Production Baselines Parity\n\n")

        v06 = self.results.get("TotalReclaw-v0.6")
        openclaw = self.results.get("OpenClaw-Hybrid")
        qmd = self.results.get("QMD-Hybrid")

        if v06:
            f.write("### F1 Score Comparison\n\n")

            baselines = []
            if openclaw:
                baselines.append(("OpenClaw-Hybrid", openclaw))
            if qmd:
                baselines.append(("QMD-Hybrid", qmd))

            for name, baseline in baselines:
                f1_diff = v06.f1_at_5 - baseline.f1_at_5
                mrr_diff = v06.mrr - baseline.mrr
                ndcg_diff = v06.ndcg_at_5 - baseline.ndcg_at_5

                status = "✓ PARITY" if f1_diff >= 0 else "✗ BELOW"
                f.write(f"#### {status}: {name}\n\n")
                f.write(f"| Metric | TotalReclaw v0.6 | {name} | Delta |\n")
                f.write(f"|--------|----------------|----------|-------|\n")
                f.write(f"| F1@5 | {v06.f1_at_5:.3f} | {baseline.f1_at_5:.3f} | {f1_diff:+.3f} |\n")
                f.write(f"| MRR | {v06.mrr:.3f} | {baseline.mrr:.3f} | {mrr_diff:+.3f} |\n")
                f.write(f"| NDCG@5 | {v06.ndcg_at_5:.3f} | {baseline.ndcg_at_5:.3f} | {ndcg_diff:+.3f} |\n")
                f.write("\n")

    def _write_e2ee_overhead_md(self, f):
        """Write E2EE overhead analysis."""

        f.write("## E2EE Overhead Analysis\n\n")

        v06 = self.results.get("TotalReclaw-v0.6")
        openclaw = self.results.get("OpenClaw-Hybrid")
        qmd = self.results.get("QMD-Hybrid")

        if v06:
            f.write("### Latency Impact of E2EE\n\n")

            if openclaw:
                overhead = v06.latency_p50_ms - openclaw.latency_p50_ms
                overhead_pct = (overhead / openclaw.latency_p50_ms * 100) if openclaw.latency_p50_ms > 0 else 0
                f.write(f"**vs OpenClaw-Hybrid:** +{overhead:.1f}ms ({overhead_pct:+.1f}%)\n")

            if qmd:
                overhead = v06.latency_p50_ms - qmd.latency_p50_ms
                overhead_pct = (overhead / qmd.latency_p50_ms * 100) if qmd.latency_p50_ms > 0 else 0
                f.write(f"**vs QMD-Hybrid:** +{overhead:.1f}ms ({overhead_pct:+.1f}%)\n")

            f.write("\n")

            f.write("### Analysis\n\n")
            f.write(f"TotalReclaw v0.6 operates at ~{v06.latency_p50_ms:.0f}ms median latency. ")
            f.write("This includes:\n")
            f.write("- Client-side encryption\n")
            f.write("- Server-side encrypted search (2-pass E2EE)\n")
            f.write("- Client-side decryption\n")
            f.write("- Query expansion with LLM\n\n")

    def _write_query_expansion_md(self, f):
        """Write query expansion impact analysis."""

        f.write("## Query Expansion Impact\n\n")

        v05 = self.results.get("TotalReclaw-v0.5")
        v06 = self.results.get("TotalReclaw-v0.6")

        if v05 and v06:
            # v0.6 includes query expansion, v0.5 doesn't
            f1_improvement = v06.f1_at_5 - v05.f1_at_5
            mrr_improvement = v06.mrr - v05.mrr

            f.write("### Effect of Adding Query Expansion (v0.5 → v0.6)\n\n")
            f.write(f"- **F1@5:** {v05.f1_at_5:.3f} → {v06.f1_at_5:.3f} ({f1_improvement:+.3f})\n")
            f.write(f"- **MRR:** {v05.mrr:.3f} → {v06.mrr:.3f} ({mrr_improvement:+.3f})\n")
            f.write(f"- **Latency:** {v05.latency_p50_ms:.1f}ms → {v06.latency_p50_ms:.1f}ms (+{v06.latency_p50_ms - v05.latency_p50_ms:.1f}ms)\n\n")

            f.write("### Analysis\n\n")
            if f1_improvement > 0:
                f.write(f"Query expansion provides a **{f1_improvement:.1%} improvement** in F1 score, ")
                f.write("justifying the added latency cost.\n\n")
            else:
                f.write(f"Query expansion does not significantly improve F1 in this evaluation. ")
                f.write("Consider reviewing the query expansion strategy.\n\n")

    def _write_recommendations_md(self, f):
        """Write recommendations section."""

        f.write("## Recommendations\n\n")

        decision = self.make_go_no_go_decision()

        if decision['decision'] == "GO":
            f.write("### ✅ Proceed to Development\n\n")
            f.write("TotalReclaw v0.6 demonstrates:\n\n")
            f.write("- Competitive search accuracy with production baselines\n")
            f.write("- Successful implementation of E2EE with query expansion\n")
            f.write("- Acceptable latency for real-world use cases\n\n")
            f.write("**Next Steps:**\n")
            f.write("1. Begin MVP development with v0.6 architecture\n")
            f.write("2. Implement production-grade key management\n")
            f.write("3. Set up monitoring and observability\n")
            f.write("4. Conduct user acceptance testing\n")

        elif decision['decision'] == "MODIFY":
            f.write("### ⚠️ Adjust Before Proceeding\n\n")
            f.write("TotalReclaw v0.6 shows promise but requires improvements:\n\n")
            for warning in decision['warnings']:
                f.write(f"- {warning}\n")
            f.write("\n**Recommended Actions:**\n")
            f.write("1. Address the concerns listed above\n")
            f.write("2. Re-run evaluation with improvements\n")
            f.write("3. Consider query expansion tuning\n")

        else:
            f.write("### ❌ Reconsider Architecture\n\n")
            f.write("TotalReclaw v0.6 does not meet minimum thresholds:\n\n")
            for warning in decision['warnings']:
                f.write(f"- {warning}\n")
            f.write("\n**Alternatives:**\n")
            f.write("1. Reconsider E2EE architecture complexity\n")
            f.write("2. Evaluate hybrid search alternatives\n")
            f.write("3. Consider client-side only encryption\n")

        f.write("\n")

    def _write_appendix_md(self, f):
        """Write appendix with methodology."""

        f.write("## Appendix\n\n")

        f.write("### Evaluation Methodology\n\n")
        f.write("- **Dataset:** Real WhatsApp chat export (1,170 messages)\n")
        f.write("- **Queries:** 48 test queries\n")
        f.write("- **Ground Truth:** LLM-assisted relevance judgment\n")
        f.write("- **Metrics:** P@5, R@5, F1@5, MRR, MAP, NDCG@5\n")
        f.write("- **Latency:** p50, p95, p99, mean (milliseconds)\n\n")

        f.write("### Algorithm Descriptions\n\n")
        f.write("| Algorithm | Description |\n")
        f.write("|-----------|-------------|\n")
        f.write("| BM25-Only | Keyword-based search using BM25 ranking |\n")
        f.write("| Vector-Only | Semantic search using sentence embeddings |\n")
        f.write("| OpenClaw-Hybrid | Production hybrid search baseline |\n")
        f.write("| QMD-Hybrid | Advanced hybrid with query understanding |\n")
        f.write("| TotalReclaw-v0.2 | 2-pass E2EE without query expansion |\n")
        f.write("| TotalReclaw-v0.5 | 3-pass E2EE without query expansion |\n")
        f.write("| TotalReclaw-v0.6 | 3-pass E2EE with LLM query expansion |\n\n")

        f.write(f"### Test Environment\n\n")
        f.write(f"- **Evaluation Date:** {datetime.now().strftime('%Y-%m-%d')}\n")
        f.write(f"- **Testbed Version:** v2.0 Real-World Data\n")
        f.write(f"- **Total Queries Evaluated:** {sum(r.queries_evaluated for r in self.results.values()) // len(self.results) if self.results else 0}\n\n")

    def _write_html_summary(self, output_path: Path):
        """Generate HTML executive summary."""

        decision = self.make_go_no_go_decision()
        v06 = self.results.get("TotalReclaw-v0.6")
        openclaw = self.results.get("OpenClaw-Hybrid")
        qmd = self.results.get("QMD-Hybrid")

        # Decision colors
        colors = {
            "GO": ("#10b981", "#d1fae5", "PROCEED TO DEVELOPMENT"),
            "MODIFY": ("#f59e0b", "#fef3c7", "ADJUST ARCHITECTURE"),
            "NO-GO": ("#ef4444", "#fee2e2", "RECONSIDER ARCHITECTURE"),
            "PENDING": ("#6b7280", "#f3f4f6", "PENDING EVALUATION"),
        }
        primary_color, bg_color, action = colors.get(decision['decision'], colors["PENDING"])

        sorted_results = self.get_sorted_results("f1")

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TotalReclaw v2.0 Evaluation - Executive Summary</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            color: #1f2937;
            background: #f9fafb;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
        header {{
            text-align: center;
            padding: 40px 20px;
            background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%);
            color: white;
            border-radius: 12px;
            margin-bottom: 30px;
        }}
        header h1 {{ font-size: 2.5rem; margin-bottom: 10px; }}
        header p {{ font-size: 1.1rem; opacity: 0.9; }}
        .decision-hero {{
            background: {bg_color};
            border-left: 6px solid {primary_color};
            border-radius: 8px;
            padding: 30px;
            margin-bottom: 30px;
            text-align: center;
        }}
        .decision-badge {{
            display: inline-block;
            background: {primary_color};
            color: white;
            padding: 12px 30px;
            border-radius: 50px;
            font-size: 1.5rem;
            font-weight: bold;
            margin-bottom: 20px;
        }}
        .action {{
            font-size: 1.8rem;
            color: {primary_color};
            font-weight: bold;
            margin: 20px 0;
        }}
        .card {{
            background: white;
            border-radius: 12px;
            padding: 25px;
            margin-bottom: 20px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        .card h2 {{
            color: #1e3a8a;
            margin-bottom: 20px;
            font-size: 1.4rem;
            border-bottom: 2px solid #e5e7eb;
            padding-bottom: 10px;
        }}
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
        }}
        .metric-card {{
            background: #f8fafc;
            border-radius: 8px;
            padding: 20px;
            text-align: center;
        }}
        .metric-card .label {{ font-size: 0.9rem; color: #6b7280; }}
        .metric-card .value {{ font-size: 2rem; font-weight: bold; color: #1e3a8a; }}
        .metric-card .delta {{ font-size: 0.9rem; margin-top: 5px; }}
        .delta.positive {{ color: #10b981; }}
        .delta.negative {{ color: #ef4444; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 15px; }}
        th, td {{ padding: 12px 15px; text-align: left; border-bottom: 1px solid #e5e7eb; }}
        th {{ background: #f3f4f6; font-weight: 600; }}
        tr:hover {{ background: #f9fafb; }}
        .medal {{ margin-right: 5px; }}
        .insights {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; }}
        .insight {{
            background: #f0fdf4;
            border-left: 4px solid #10b981;
            padding: 15px;
            border-radius: 6px;
        }}
        .insight.warning {{ background: #fef3c7; border-left-color: #f59e0b; }}
        .insight.error {{ background: #fee2e2; border-left-color: #ef4444; }}
        .insight h4 {{ color: #374151; margin-bottom: 8px; }}
        footer {{
            text-align: center;
            padding: 30px;
            color: #6b7280;
            font-size: 0.9rem;
        }}
        @media print {{ body {{ background: white; }} .container {{ max-width: 100%; }} }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>TotalReclaw v2.0</h1>
            <p>Real-World Data Evaluation - Executive Summary</p>
            <p style="margin-top: 10px; font-size: 0.9rem;">Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </header>

        <div class="decision-hero">
            <div class="decision-badge">{decision['decision']}</div>
            <div class="action">{action}</div>
            <p style="margin-top: 20px; color: #4b5563;">{decision.get('rationale', 'Evaluation pending')}</p>
        </div>

        <div class="card">
            <h2>Key Metrics</h2>
            <div class="metrics-grid">
"""

        if v06:
            html += f"""
                <div class="metric-card">
                    <div class="label">F1 Score</div>
                    <div class="value">{v06.f1_at_5:.3f}</div>
                    <div class="delta">TotalReclaw v0.6</div>
                </div>
                <div class="metric-card">
                    <div class="label">MRR</div>
                    <div class="value">{v06.mrr:.3f}</div>
                    <div class="delta">Mean Reciprocal Rank</div>
                </div>
                <div class="metric-card">
                    <div class="label">Latency p50</div>
                    <div class="value">{v06.latency_p50_ms:.0f}ms</div>
                    <div class="delta">Median response time</div>
                </div>
"""

        html += """
            </div>
        </div>

        <div class="card">
            <h2>Algorithm Leaderboard</h2>
            <table>
                <thead>
                    <tr>
                        <th>Rank</th>
                        <th>Algorithm</th>
                        <th>F1 Score</th>
                        <th>Latency (ms)</th>
                    </tr>
                </thead>
                <tbody>
"""

        medals = ['🥇', '🥈', '🥉']
        for i, r in enumerate(sorted_results[:7]):
            medal = medals[i] if i < 3 else ''
            html += f"""
                    <tr>
                        <td>{medal} {i+1}</td>
                        <td>{r.name}</td>
                        <td>{r.f1_at_5:.3f}</td>
                        <td>{r.latency_p50_ms:.0f}</td>
                    </tr>
"""

        html += """
                </tbody>
            </table>
        </div>

        <div class="card">
            <h2>Key Insights</h2>
            <div class="insights">
"""

        # Add insight cards
        insights = []

        if v06:
            if v06.f1_at_5 >= 0.22:
                insights.append({
                    'title': 'Strong Accuracy',
                    'text': f'F1 score of {v06.f1_at_5:.3f} demonstrates competitive retrieval performance.',
                    'type': 'success'
                })
            else:
                insights.append({
                    'title': 'Accuracy Concern',
                    'text': f'F1 score of {v06.f1_at_5:.3f} is below target. Consider optimization.',
                    'type': 'warning'
                })

        if v06 and v06.latency_p50_ms > 500:
            insights.append({
                'title': 'High Latency',
                'text': f'Median latency of {v06.latency_p50_ms:.0f}ms may impact user experience.',
                'type': 'warning'
            })

        if v06 and openclaw:
            f1_gap = v06.f1_at_5 - openclaw.f1_at_5
            if f1_gap >= 0:
                insights.append({
                    'title': 'Parity Achieved',
                    'text': f'Matches or exceeds OpenClaw-Hybrid baseline ({f1_gap:+.3f} F1 gap).',
                    'type': 'success'
                })
            else:
                insights.append({
                    'title': 'Gap to Baseline',
                    'text': f'Lags OpenClaw-Hybrid by {abs(f1_gap):.3f} F1 points.',
                    'type': 'error'
                })

        for insight in insights:
            insight_class = "error" if insight.get('type') == 'error' else ("warning" if insight.get('type') == 'warning' else "")
            html += f"""
                <div class="insight {insight_class}">
                    <h4>{insight['title']}</h4>
                    <p>{insight['text']}</p>
                </div>
"""

        html += """
            </div>
        </div>

        <div class="card">
            <h2>Recommendations</h2>
            <ul style="padding-left: 20px;">
"""

        if decision['decision'] == "GO":
            recommendations = [
                "<strong>Proceed with MVP development</strong> using TotalReclaw v0.6 architecture",
                "Implement production-grade E2EE with proper key management",
                "Set up monitoring for latency metrics in production",
            ]
        elif decision['decision'] == "MODIFY":
            recommendations = [
                "<strong>Address accuracy gaps</strong> before proceeding to development",
            ] + [f"Fix: {w}" for w in decision.get('warnings', [])]
        else:
            recommendations = [
                "<strong>Reconsider the E2EE architecture</strong> approach",
                "Evaluate alternative hybrid search strategies",
                "Consider if zero-knowledge requirements can be relaxed",
            ]

        for rec in recommendations:
            html += f"                <li style='margin-bottom: 10px;'>{rec}</li>\n"

        html += """
            </ul>
        </div>

        <footer>
            <p>TotalReclaw v2.0 Evaluation | Confidential</p>
            <p>For detailed technical analysis, see EVALUATION_REPORT.md</p>
        </footer>
    </div>
</body>
</html>
"""

        with open(output_path, 'w') as f:
            f.write(html)


def main():
    """Main entry point."""

    print("=" * 70)
    print("TotalReclaw v2.0 Report Generator")
    print("=" * 70)

    generator = V2ReportGenerator()

    if not generator.load_results():
        print("Failed to load results")
        return 1

    print()

    md_path, html_path = generator.generate_reports()

    print()
    print("=" * 70)
    print("Reports Generated Successfully")
    print("=" * 70)
    print(f"Markdown: {md_path}")
    print(f"HTML:     {html_path}")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    exit(main())
