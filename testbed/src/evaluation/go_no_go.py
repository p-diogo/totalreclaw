"""
Go/No-Go decision framework for TotalReclaw testbed.

Implements the decision criteria from the testbed specification.
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from enum import Enum


class Decision(Enum):
    """Go/No-Go decision values."""
    GO = "GO"
    MODIFY = "MODIFY"
    NO_GO = "NO-GO"


@dataclass
class DecisionCriteria:
    """
    Criteria for Go/No-Go decision.

    Based on TotalReclaw testbed specification:

    **GO (Proceed to Development):**
    - F1 score >0.80 OR
    - Within 5% of QMD's F1 score OR
    - MRR >0.70 with recall >0.75
    - **AND OpenClaw compatibility met**

    **MODIFY (Adjust Architecture):**
    - F1 score 0.75-0.80 OR
    - Within 10% of QMD but with clear gap identified
    - MRR 0.65-0.70
    - **OR OpenClaw compatibility needs work** (fixable)

    **NO-Go (Reconsider Architecture):**
    - F1 score <0.75 OR
    - >15% gap from QMD's F1 score OR
    - MRR <0.65
    - **OR OpenClaw compatibility fundamentally broken** (unfixable)
    """

    # Accuracy thresholds
    min_f1_for_go: float = 0.80
    min_f1_for_modify: float = 0.75
    min_mrr_for_go: float = 0.70
    min_mrr_for_modify: float = 0.65
    min_recall_for_go: float = 0.75

    # Comparison thresholds (relative to baseline)
    max_gap_for_go: float = 0.05  # 5%
    max_gap_for_modify: float = 0.10  # 10%
    max_gap_for_no_go: float = 0.15  # 15%

    # Latency targets
    max_latency_p50: float = 800  # ms
    max_latency_p95: float = 1500  # ms

    # OpenClaw compatibility
    min_openclaw_f1: float = 0.90  # For imported data
    min_round_trip_f1: float = 0.95  # Content preservation

    # Inter-annotator agreement
    min_fleiss_kappa: float = 0.70


@dataclass
class GoNoGoResult:
    """Result of Go/No-Go evaluation."""

    decision: Decision
    rationale: str
    passed_criteria: List[str]
    failed_criteria: List[str]
    warnings: List[str]

    # Key metrics
    totalreclaw_f1: float
    baseline_f1: float  # QMD or best baseline
    f1_gap: float
    totalreclaw_mrr: float
    totalreclaw_recall: float
    latency_p50: float

    # Compatibility metrics
    openclaw_compatibility_met: bool = False
    import_f1: float = 0.0
    round_trip_f1: float = 0.0

    # Ground truth quality
    fleiss_kappa: float = 0.0
    ground_truth_quality: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'decision': self.decision.value,
            'rationale': self.rationale,
            'passed_criteria': self.passed_criteria,
            'failed_criteria': self.failed_criteria,
            'warnings': self.warnings,
            'totalreclaw_f1': self.totalreclaw_f1,
            'baseline_f1': self.baseline_f1,
            'f1_gap': self.f1_gap,
            'totalreclaw_mrr': self.totalreclaw_mrr,
            'totalreclaw_recall': self.totalreclaw_recall,
            'latency_p50': self.latency_p50,
            'openclaw_compatibility_met': self.openclaw_compatibility_met,
            'import_f1': self.import_f1,
            'round_trip_f1': self.round_trip_f1,
            'fleiss_kappa': self.fleiss_kappa,
            'ground_truth_quality': self.ground_truth_quality
        }


class GoNoGoDecision:
    """
    Framework for making Go/No-Go decisions based on testbed results.

    Example:
        >>> results = EvaluationResults(...)
        >>> decision_framework = GoNoGoDecision()
        >>> result = decision_framework.evaluate(
        ...     results=results,
        ...     totalreclaw_algo='totalreclaw_v05',
        ...     baseline_algo='qmd_hybrid'
        ... )
        >>> print(result.decision)  # Decision.GO
        >>> print(result.rationale)
    """

    def __init__(self, criteria: DecisionCriteria = None):
        """
        Initialize decision framework.

        Args:
            criteria: Decision criteria (uses defaults if None)
        """
        self.criteria = criteria or DecisionCriteria()

    def evaluate(
        self,
        results: Dict[str, Any],
        totalreclaw_algo: str,
        baseline_algo: str = 'qmd_hybrid',
        compatibility_results: Dict[str, float] = None
    ) -> GoNoGoResult:
        """
        Make Go/No-Go decision based on evaluation results.

        Args:
            results: Dictionary with algorithm results
            totalreclaw_algo: Name of TotalReclaw algorithm to evaluate
            baseline_algo: Name of baseline algorithm for comparison
            compatibility_results: Optional dict with import_f1, round_trip_f1

        Returns:
            GoNoGoResult with decision and rationale
        """
        passed = []
        failed = []
        warnings = []

        # Extract metrics
        om = results.get(totalreclaw_algo, {})
        baseline = results.get(baseline_algo, {})

        om_f1 = om.get('mean_f1', 0.0)
        baseline_f1 = baseline.get('mean_f1', 0.0)
        f1_gap = abs(om_f1 - baseline_f1)

        om_mrr = om.get('mrr', 0.0)
        om_recall = om.get('mean_recall', 0.0)
        latency_p50 = om.get('latency_p50', 0.0)

        # Get compatibility metrics
        import_f1 = compatibility_results.get('import_f1', 0.0) if compatibility_results else 0.0
        round_trip_f1 = compatibility_results.get('round_trip_f1', 0.0) if compatibility_results else 0.0
        openclaw_compat = (
            import_f1 >= self.criteria.min_openclaw_f1 and
            round_trip_f1 >= self.criteria.min_round_trip_f1
        )

        # Check ground truth quality
        fleiss_kappa = results.get('fleiss_kappa', 0.0)
        gt_quality = self._assess_ground_truth_quality(fleiss_kappa)

        # === Evaluate Accuracy Criteria ===

        # Check F1 score
        if om_f1 >= self.criteria.min_f1_for_go:
            passed.append(f"F1 score ({om_f1:.3f}) >= {self.criteria.min_f1_for_go}")
        elif om_f1 >= self.criteria.min_f1_for_modify:
            warnings.append(f"F1 score ({om_f1:.3f}) in MODIFY range")
        else:
            failed.append(f"F1 score ({om_f1:.3f}) below {self.criteria.min_f1_for_modify}")

        # Check F1 gap to baseline
        if f1_gap <= self.criteria.max_gap_for_go:
            passed.append(f"F1 gap to baseline ({f1_gap:.1%}) <= {self.criteria.max_gap_for_go:.0%}")
        elif f1_gap <= self.criteria.max_gap_for_modify:
            warnings.append(f"F1 gap to baseline ({f1_gap:.1%}) in MODIFY range")
        elif f1_gap > self.criteria.max_gap_for_no_go:
            failed.append(f"F1 gap to baseline ({f1_gap:.1%}) exceeds {self.criteria.max_gap_for_no_go:.0%}")

        # Check MRR + Recall combo
        if om_mrr >= self.criteria.min_mrr_for_go and om_recall >= self.criteria.min_recall_for_go:
            passed.append(f"MRR ({om_mrr:.3f}) and Recall ({om_recall:.3f}) meet thresholds")
        elif om_mrr >= self.criteria.min_mrr_for_modify:
            warnings.append(f"MRR ({om_mrr:.3f}) in MODIFY range")
        else:
            failed.append(f"MRR ({om_mrr:.3f}) below {self.criteria.min_mrr_for_modify}")

        # === Evaluate Latency ===

        if latency_p50 <= self.criteria.max_latency_p50:
            passed.append(f"Latency p50 ({latency_p50:.0f}ms) <= {self.criteria.max_latency_p50}ms")
        else:
            warnings.append(f"Latency p50 ({latency_p50:.0f}ms) exceeds target")

        # === Evaluate OpenClaw Compatibility ===

        if openclaw_compat:
            passed.append(f"OpenClaw compatibility met (import F1: {import_f1:.3f}, round-trip F1: {round_trip_f1:.3f})")
        else:
            failed.append("OpenClaw compatibility not met")

        # === Make Decision ===

        decision = self._make_decision(passed, failed, warnings, openclaw_compat)

        # Generate rationale
        rationale = self._generate_rationale(
            decision, passed, failed, warnings,
            om_f1, baseline_f1, f1_gap, om_mrr, om_recall,
            latency_p50, openclaw_compat, gt_quality
        )

        return GoNoGoResult(
            decision=decision,
            rationale=rationale,
            passed_criteria=passed,
            failed_criteria=failed,
            warnings=warnings,
            totalreclaw_f1=om_f1,
            baseline_f1=baseline_f1,
            f1_gap=f1_gap,
            totalreclaw_mrr=om_mrr,
            totalreclaw_recall=om_recall,
            latency_p50=latency_p50,
            openclaw_compatibility_met=openclaw_compat,
            import_f1=import_f1,
            round_trip_f1=round_trip_f1,
            fleiss_kappa=fleiss_kappa,
            ground_truth_quality=gt_quality
        )

    def _make_decision(
        self,
        passed: List[str],
        failed: List[str],
        warnings: List[str],
        openclaw_compat: bool
    ) -> Decision:
        """Make final decision based on criteria."""

        # Critical failures lead to NO-GO
        critical_failures = [
            f for f in failed
            if 'F1 score below' in f or 'F1 gap exceeds' in f and 'compatibility' not in f.lower()
        ]

        if critical_failures and not openclaw_compat:
            return Decision.NO_GO

        # Check for GO criteria
        accuracy_go = any('F1 score' in p or 'F1 gap' in p or 'MRR' in p for p in passed)

        if accuracy_go and openclaw_compat:
            return Decision.GO

        # Check for MODIFY
        if warnings or not openclaw_compat:
            return Decision.MODIFY

        # Default to GO if mostly passed
        if len(passed) >= len(failed):
            return Decision.GO

        return Decision.MODIFY

    def _generate_rationale(
        self,
        decision: Decision,
        passed: List[str],
        failed: List[str],
        warnings: List[str],
        om_f1: float,
        baseline_f1: float,
        f1_gap: float,
        om_mrr: float,
        om_recall: float,
        latency_p50: float,
        openclaw_compat: bool,
        gt_quality: str
    ) -> str:
        """Generate human-readable rationale."""

        rationale = f"**Decision: {decision.value}**\n\n"

        rationale += "## Summary\n\n"
        rationale += f"- TotalReclaw F1: {om_f1:.3f} (baseline: {baseline_f1:.3f}, gap: {f1_gap:.1%})\n"
        rationale += f"- TotalReclaw MRR: {om_mrr:.3f}, Recall: {om_recall:.3f}\n"
        rationale += f"- Latency p50: {latency_p50:.0f}ms\n"
        rationale += f"- OpenClaw compatibility: {'MET' if openclaw_compat else 'NOT MET'}\n"
        rationale += f"- Ground truth quality: {gt_quality}\n\n"

        rationale += "## Passed Criteria\n\n"
        for p in passed:
            rationale += f"- ✓ {p}\n"

        if warnings:
            rationale += "\n## Warnings\n\n"
            for w in warnings:
                rationale += f"- ⚠ {w}\n"

        if failed:
            rationale += "\n## Failed Criteria\n\n"
            for f in failed:
                rationale += f"- ✗ {f}\n"

        rationale += "\n## Recommendation\n\n"

        if decision == Decision.GO:
            rationale += ("TotalReclaw testbed results meet the criteria for proceeding to MVP "
                         "development. The hybrid E2EE architecture demonstrates competitive "
                         "search accuracy while maintaining zero-knowledge encryption properties.")
        elif decision == Decision.MODIFY:
            rationale += ("TotalReclaw shows promise but requires targeted improvements before "
                         "proceeding. Address the failed criteria and warnings above, then "
                         "re-run the testbed evaluation.")
        else:  # NO_GO
            rationale += ("TotalReclaw testbed results do not meet minimum thresholds. "
                         "Consider architectural alternatives or pivoting to a different approach.")

        return rationale

    def _assess_ground_truth_quality(self, fleiss_kappa: float) -> str:
        """Assess ground truth quality based on Fleiss' kappa."""
        if fleiss_kappa >= 0.80:
            return "excellent"
        elif fleiss_kappa >= 0.70:
            return "good"
        elif fleiss_kappa >= 0.60:
            return "fair"
        else:
            return "poor (consider re-labeling)"
