"""
Report generation for TotalReclaw testbed evaluation.

Generates comprehensive markdown reports with tables, charts, and analysis.
"""

from typing import Dict, List, Any, Optional
from datetime import datetime
import json
import os

from .results import EvaluationResults
from .go_no_go import GoNoGoDecision, DecisionCriteria, GoNoGoResult


class ReportGenerator:
    """
    Generate comprehensive evaluation reports.

    Example:
        >>> generator = ReportGenerator()
        >>> generator.generate(results, go_no_go_result, output_dir="./reports")
    """

    def __init__(self):
        self.template_dir = os.path.join(os.path.dirname(__file__), '..', 'templates')

    def generate(
        self,
        results: EvaluationResults,
        go_no_go_result: GoNoGoResult = None,
        output_dir: str = "./reports",
        include_charts: bool = True
    ) -> str:
        """
        Generate complete evaluation report.

        Args:
            results: Evaluation results
            go_no_go_result: Optional Go/No-Go decision result
            output_dir: Output directory for report files
            include_charts: Whether to include chart generation

        Returns:
            Path to generated report
        """
        os.makedirs(output_dir, exist_ok=True)

        # Generate markdown report
        report_path = os.path.join(output_dir, f"evaluation_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md")
        self._generate_markdown_report(results, go_no_go_result, report_path)

        # Save JSON results
        json_path = os.path.join(output_dir, f"evaluation_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        results.to_json(json_path)

        # Generate charts if requested
        if include_charts:
            self._generate_charts(results, output_dir)

        return report_path

    def _generate_markdown_report(
        self,
        results: EvaluationResults,
        go_no_go_result: GoNoGoResult,
        output_path: str
    ):
        """Generate main markdown report."""

        with open(output_path, 'w') as f:
            # Title and metadata
            f.write("# TotalReclaw Testbed Evaluation Report\n\n")
            f.write(f"**Generated:** {results.timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write(f"**Dataset Size:** {results.dataset_size} memory chunks\n\n")
            f.write(f"**Test Queries:** {results.num_queries}\n\n")
            f.write(f"**Evaluators:** {results.num_evaluators}\n\n")
            f.write(f"**Fleiss' Kappa:** {results.fleiss_kappa:.3f} ({results.inter_annotator_agreement})\n\n")

            # Executive Summary
            self._write_executive_summary(f, results, go_no_go_result)

            # Overall Results
            self._write_overall_results(f, results)

            # Performance by Category
            self._write_category_breakdown(f, results)

            # Statistical Analysis
            self._write_statistical_analysis(f, results)

            # Go/No-Go Decision
            if go_no_go_result:
                self._write_go_no_go_section(f, go_no_go_result)

            # Detailed Results
            self._write_detailed_results(f, results)

            # Appendix
            self._write_appendix(f, results)

    def _write_executive_summary(
        self,
        f,
        results: EvaluationResults,
        go_no_go_result: GoNoGoResult
    ):
        """Write executive summary section."""

        f.write("## Executive Summary\n\n")

        # Get best performing algorithm
        leaderboard = results.get_leaderboard()
        if leaderboard:
            best = leaderboard[0]
            f.write(f"**Best Performing Algorithm:** {best['algorithm']} (F1: {best['f1']:.3f})\n\n")

        # Go/No-Go summary
        if go_no_go_result:
            f.write(f"**Recommendation:** {go_no_go_result.decision.value}\n\n")
            f.write(f"{go_no_go_result.rationale}\n\n")
        else:
            f.write("**Recommendation:** Pending Go/No-Go analysis\n\n")

        # Key findings
        f.write("### Key Findings\n\n")

        # Find best/worst by category
        for category in results.categories:
            category_results = []
            for name, result in results.algorithm_results.items():
                if category in result.metrics_by_category:
                    cat_metrics = result.metrics_by_category[category]
                    category_results.append({
                        'algorithm': name,
                        'f1': cat_metrics['f1']
                    })

            if category_results:
                category_results.sort(key=lambda x: x['f1'], reverse=True)
                best_cat = category_results[0]
                f.write(f"- **{category}:** {best_cat['algorithm']} leads with F1={best_cat['f1']:.3f}\n")

        f.write("\n")

    def _write_overall_results(self, f, results: EvaluationResults):
        """Write overall comparison table."""

        f.write("## Overall Results\n\n")
        f.write(results.get_comparison_table())
        f.write("\n")

        # Leaderboard
        f.write("### Leaderboard (by F1 Score)\n\n")
        leaderboard = results.get_leaderboard()
        for i, entry in enumerate(leaderboard, 1):
            f.write(f"{i}. **{entry['algorithm']}**\n")
            f.write(f"   - F1: {entry['f1']:.3f} | Precision: {entry['precision']:.3f} | ")
            f.write(f"Recall: {entry['recall']:.3f} | MRR: {entry['mrr']:.3f}\n")
            f.write(f"   - Latency p50: {entry['latency_p50']:.0f}ms\n\n")

    def _write_category_breakdown(self, f, results: EvaluationResults):
        """Write performance breakdown by query category."""

        f.write("## Performance by Query Category\n\n")

        for category in results.categories:
            f.write(f"### {category}\n\n")

            # Table header
            f.write("| Algorithm | F1 | Precision | Recall | MRR |\n")
            f.write("|-----------|-----|-----------|--------|-----|\n")

            # Table rows
            category_data = []
            for name, result in results.algorithm_results.items():
                if category in result.metrics_by_category:
                    metrics = result.metrics_by_category[category]
                    category_data.append({
                        'name': name,
                        **metrics
                    })

            category_data.sort(key=lambda x: x['f1'], reverse=True)

            for data in category_data:
                f.write(f"| {data['name']} | {data['f1']:.3f} | {data['precision']:.3f} | ")
                f.write(f"{data['recall']:.3f} | {data['mrr']:.3f} |\n")

            f.write("\n")

    def _write_statistical_analysis(self, f, results: EvaluationResults):
        """Write statistical significance tests."""

        f.write("## Statistical Analysis\n\n")

        if not results.pairwise_comparisons:
            f.write("*No pairwise comparisons available.*\n\n")
            return

        f.write("### Pairwise Algorithm Comparisons\n\n")
        f.write("Tests performed on F1 scores using paired t-test and Wilcoxon signed-rank test.\n\n")

        for pair_name, comparison in results.pairwise_comparisons.items():
            algorithms = pair_name.split('_vs_')
            f.write(f"#### {algorithms[0]} vs {algorithms[1]}\n\n")

            ttest = comparison.get('t_test', {})
            f.write(f"- **Paired t-test:** t={ttest.get('statistic', 0):.3f}, ")
            f.write(f"p={ttest.get('p_value', 1):.4f} ({ttest.get('interpretation', 'N/A')})\n")

            wilcoxon = comparison.get('wilcoxon', {})
            f.write(f"- **Wilcoxon signed-rank:** statistic={wilcoxon.get('statistic', 0):.1f}, ")
            f.write(f"p={wilcoxon.get('p_value', 1):.4f}\n")

            effect = comparison.get('effect_size', {})
            f.write(f"- **Effect size (Cohen's d):** {effect.get('effect_size', 0):.3f} ")
            f.write(f"({effect.get('interpretation', 'N/A')})\n")

            f.write(f"- **Mean difference:** {comparison.get('mean_difference', 0):.4f}\n\n")

    def _write_go_no_go_section(self, f, go_no_go_result: GoNoGoResult):
        """Write Go/No-Go decision section."""

        f.write("## Go/No-Go Decision\n\n")

        # Decision badge
        decision_emoji = {
            'GO': '✅',
            'MODIFY': '⚠️',
            'NO-GO': '❌'
        }
        emoji = decision_emoji.get(go_no_go_result.decision.value, '')
        f.write(f"### {emoji} Decision: {go_no_go_result.decision.value}\n\n")

        # Rationale
        f.write(f"{go_no_go_result.rationale}\n\n")

        # Criteria breakdown
        f.write("### Criteria Breakdown\n\n")
        f.write("#### Passed Criteria\n\n")
        for criterion in go_no_go_result.passed_criteria:
            f.write(f"- ✓ {criterion}\n")

        if go_no_go_result.warnings:
            f.write("\n#### Warnings\n\n")
            for warning in go_no_go_result.warnings:
                f.write(f"- ⚠ {warning}\n")

        if go_no_go_result.failed_criteria:
            f.write("\n#### Failed Criteria\n\n")
            for criterion in go_no_go_result.failed_criteria:
                f.write(f"- ✗ {criterion}\n")

        f.write("\n")

        # Key metrics summary
        f.write("### Key Metrics\n\n")
        f.write(f"- **TotalReclaw F1:** {go_no_go_result.totalreclaw_f1:.3f}\n")
        f.write(f"- **Baseline F1:** {go_no_go_result.baseline_f1:.3f}\n")
        f.write(f"- **F1 Gap:** {go_no_go_result.f1_gap:.1%}\n")
        f.write(f"- **TotalReclaw MRR:** {go_no_go_result.totalreclaw_mrr:.3f}\n")
        f.write(f"- **TotalReclaw Recall:** {go_no_go_result.totalreclaw_recall:.3f}\n")
        f.write(f"- **Latency p50:** {go_no_go_result.latency_p50:.0f}ms\n")
        f.write(f"- **OpenClaw Compatibility:** {'MET' if go_no_go_result.openclaw_compatibility_met else 'NOT MET'}\n")
        f.write(f"- **Ground Truth Quality:** {go_no_go_result.ground_truth_quality} (κ={go_no_go_result.fleiss_kappa:.3f})\n\n")

    def _write_detailed_results(self, f, results: EvaluationResults):
        """Write detailed per-query results."""

        f.write("## Detailed Results\n\n")
        f.write("*Per-query results available in JSON output file.*\n\n")

        # Sample queries
        f.write("### Sample Query Results\n\n")

        # Show a few example queries with results
        sample_queries = results.all_query_results[:10]
        if sample_queries:
            for qr in sample_queries:
                f.write(f"#### Query: {qr.query_text}\n\n")
                f.write(f"- **Category:** {qr.category}\n")
                f.write(f"- **Algorithm:** {qr.algorithm_name}\n")
                f.write(f"- **Retrieved:** {qr.retrieved[:3] if len(qr.retrieved) > 3 else qr.retrieved}\n")
                f.write(f"- **Relevant:** {len(qr.relevant)} documents\n")
                f.write(f"- **F1:** {qr.f1:.3f} | **MRR:** {qr.rr:.3f}\n")
                f.write(f"- **Latency:** {qr.latency_ms:.0f}ms\n\n")

    def _write_appendix(self, f, results: EvaluationResults):
        """Write appendix with methodology and metadata."""

        f.write("## Appendix\n\n")

        f.write("### Methodology\n\n")
        f.write("#### Metrics\n\n")
        f.write("- **Precision:** |Relevant Retrieved| / |All Retrieved|\n")
        f.write("- **Recall:** |Relevant Retrieved| / |All Relevant|\n")
        f.write("- **F1 Score:** 2 × (Precision × Recall) / (Precision + Recall)\n")
        f.write("- **MRR:** Mean of 1/rank for first relevant result\n")
        f.write("- **MAP:** Mean of Average Precision across all queries\n")
        f.write("- **NDCG:** Normalized Discounted Cumulative Gain\n\n")

        f.write("#### Statistical Tests\n\n")
        f.write("- **Paired t-test:** Tests if mean difference between algorithms is significant\n")
        f.write("- **Wilcoxon signed-rank:** Non-parametric alternative to t-test\n")
        f.write("- **Cohen's d:** Effect size measure (small=0.2, medium=0.5, large=0.8)\n\n")

        f.write("### Dataset Information\n\n")
        f.write(f"- **Total memories:** {results.dataset_size}\n")
        f.write(f"- **Total queries:** {results.num_queries}\n")
        f.write(f"- **Categories:** {', '.join(results.categories)}\n")
        f.write(f"- **Evaluators:** {results.num_evaluators}\n")
        f.write(f"- **Inter-annotator agreement:** κ={results.fleiss_kappa:.3f}\n\n")

        f.write("### Algorithms Evaluated\n\n")
        for name in results.algorithm_results.keys():
            f.write(f"- **{name}**\n")

    def _generate_charts(self, results: EvaluationResults, output_dir: str):
        """Generate visualization charts."""

        try:
            import matplotlib.pyplot as plt
            import matplotlib
            matplotlib.use('Agg')  # Non-interactive backend

            # Create figure with subplots
            fig, axes = plt.subplots(2, 2, figsize=(14, 10))
            fig.suptitle('TotalReclaw Testbed Evaluation Results', fontsize=16)

            # Algorithm names and metrics
            algos = list(results.algorithm_results.keys())
            metrics = ['mean_precision', 'mean_recall', 'mean_f1', 'mrr', 'map_score']

            # Prepare data
            data = {metric: [] for metric in metrics}
            for name in algos:
                result = results.algorithm_results[name]
                for metric in metrics:
                    data[metric].append(getattr(result, metric))

            # Plot 1: Overall metrics comparison (bar chart)
            ax1 = axes[0, 0]
            x = range(len(algos))
            width = 0.15
            for i, metric in enumerate(['mean_precision', 'mean_recall', 'mean_f1']):
                ax1.bar([xi + i * width for xi in x], data[metric], width,
                       label=metric.replace('mean_', '').title())
            ax1.set_xlabel('Algorithm')
            ax1.set_ylabel('Score')
            ax1.set_title('Overall Metrics Comparison')
            ax1.set_xticks([xi + width for xi in x])
            ax1.set_xticklabels(algos, rotation=45, ha='right')
            ax1.legend()
            ax1.set_ylim([0, 1])

            # Plot 2: Ranking metrics (MRR, MAP)
            ax2 = axes[0, 1]
            x = range(len(algos))
            width = 0.35
            ax2.bar([xi - width/2 for xi in x], data['mrr'], width, label='MRR')
            ax2.bar([xi + width/2 for xi in x], data['map_score'], width, label='MAP')
            ax2.set_xlabel('Algorithm')
            ax2.set_ylabel('Score')
            ax2.set_title('Ranking Metrics')
            ax2.set_xticks(x)
            ax2.set_xticklabels(algos, rotation=45, ha='right')
            ax2.legend()
            ax2.set_ylim([0, 1])

            # Plot 3: Latency comparison
            ax3 = axes[1, 0]
            latencies_p50 = [results.algorithm_results[name].latency_p50 for name in algos]
            latencies_p95 = [results.algorithm_results[name].latency_p95 for name in algos]
            x = range(len(algos))
            width = 0.35
            ax3.bar([xi - width/2 for xi in x], latencies_p50, width, label='p50')
            ax3.bar([xi + width/2 for xi in x], latencies_p95, width, label='p95')
            ax3.set_xlabel('Algorithm')
            ax3.set_ylabel('Latency (ms)')
            ax3.set_title('Search Latency')
            ax3.set_xticks(x)
            ax3.set_xticklabels(algos, rotation=45, ha='right')
            ax3.legend()

            # Plot 4: F1 by category (stacked or grouped)
            ax4 = axes[1, 1]
            categories = results.categories[:5]  # Limit to top 5 categories
            x = np.arange(len(algos))
            width = 0.8 / len(categories)

            for i, category in enumerate(categories):
                f1_scores = []
                for name in algos:
                    result = results.algorithm_results[name]
                    if category in result.metrics_by_category:
                        f1_scores.append(result.metrics_by_category[category]['f1'])
                    else:
                        f1_scores.append(0)
                ax4.bar(x + i * width, f1_scores, width, label=category)

            ax4.set_xlabel('Algorithm')
            ax4.set_ylabel('F1 Score')
            ax4.set_title('F1 Score by Category')
            ax4.set_xticks(x + width * (len(categories) - 1) / 2)
            ax4.set_xticklabels(algos, rotation=45, ha='right')
            ax4.legend(title='Category', bbox_to_anchor=(1.05, 1), loc='upper left')
            ax4.set_ylim([0, 1])

            plt.tight_layout()

            # Save figure
            chart_path = os.path.join(output_dir, f"evaluation_charts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
            plt.savefig(chart_path, dpi=150, bbox_inches='tight')
            plt.close()

        except ImportError:
            # matplotlib not available, skip charts
            pass
