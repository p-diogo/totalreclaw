"""
Statistical significance tests for comparing search algorithms.

Includes t-tests, Wilcoxon signed-rank tests, and bootstrap confidence intervals.
"""

from typing import List, Tuple, Dict, Any
import numpy as np
from scipy import stats


def paired_ttest(
    sample1: List[float],
    sample2: List[float],
    alpha: float = 0.05
) -> Dict[str, Any]:
    """
    Perform a paired t-test to determine if two samples are significantly different.

    The paired t-test is appropriate when comparing two algorithms on the same
    set of queries (paired observations).

    Args:
        sample1: Metric values from algorithm 1 (e.g., F1 scores per query)
        sample2: Metric values from algorithm 2
        alpha: Significance level (default: 0.05 for 95% confidence)

    Returns:
        Dictionary with t-statistic, p-value, and interpretation

    Example:
        >>> algo1_scores = [0.8, 0.75, 0.82, 0.79, 0.81]
        >>> algo2_scores = [0.75, 0.73, 0.78, 0.76, 0.77]
        >>> paired_ttest(algo1_scores, algo2_scores)
        {
            'statistic': 4.47,
            'p_value': 0.011,
            'significant': True,
            'interpretation': 'Significant difference at alpha=0.05'
        }
    """
    if len(sample1) != len(sample2):
        raise ValueError("Samples must be the same length for paired t-test")

    if len(sample1) < 2:
        return {
            'statistic': 0.0,
            'p_value': 1.0,
            'significant': False,
            'interpretation': 'Insufficient data'
        }

    statistic, p_value = stats.ttest_rel(sample1, sample2)

    return {
        'statistic': float(statistic),
        'p_value': float(p_value),
        'significant': p_value < alpha,
        'alpha': alpha,
        'interpretation': _format_p_value_interpretation(p_value, alpha)
    }


def wilcoxon_signed_rank_test(
    sample1: List[float],
    sample2: List[float],
    alpha: float = 0.05
) -> Dict[str, Any]:
    """
    Perform Wilcoxon signed-rank test (non-parametric alternative to paired t-test).

    This test is appropriate when:
    - Data is not normally distributed
    - Sample size is small
    - Data is ordinal rather than interval

    Args:
        sample1: Metric values from algorithm 1
        sample2: Metric values from algorithm 2
        alpha: Significance level

    Returns:
        Dictionary with test statistic, p-value, and interpretation

    Example:
        >>> algo1_scores = [0.8, 0.75, 0.82, 0.79, 0.81]
        >>> algo2_scores = [0.75, 0.73, 0.78, 0.76, 0.77]
        >>> wilcoxon_signed_rank_test(algo1_scores, algo2_scores)
        {
            'statistic': 0.0,
            'p_value': 0.0625,
            'significant': False,
            'interpretation': 'Not significant at alpha=0.05'
        }
    """
    if len(sample1) != len(sample2):
        raise ValueError("Samples must be the same length")

    if len(sample1) < 2:
        return {
            'statistic': 0.0,
            'p_value': 1.0,
            'significant': False,
            'interpretation': 'Insufficient data'
        }

    try:
        statistic, p_value = stats.wilcoxon(sample1, sample2)
    except ValueError:
        # All differences are zero
        return {
            'statistic': 0.0,
            'p_value': 1.0,
            'significant': False,
            'interpretation': 'No difference between samples'
        }

    return {
        'statistic': float(statistic),
        'p_value': float(p_value),
        'significant': p_value < alpha,
        'alpha': alpha,
        'interpretation': _format_p_value_interpretation(p_value, alpha)
    }


def bootstrap_confidence_interval(
    sample: List[float],
    statistic: str = 'mean',
    confidence: float = 0.95,
    n_bootstrap: int = 10000
) -> Dict[str, Any]:
    """
    Calculate bootstrap confidence interval for a statistic.

    Bootstrapping is a resampling method that doesn't assume normality.

    Args:
        sample: List of metric values
        statistic: Statistic to bootstrap ('mean', 'median', 'std')
        confidence: Confidence level (default: 0.95 for 95% CI)
        n_bootstrap: Number of bootstrap samples

    Returns:
        Dictionary with statistic, CI bounds, and bootstrap samples

    Example:
        >>> scores = [0.8, 0.75, 0.82, 0.79, 0.81, 0.77, 0.83]
        >>> bootstrap_confidence_interval(scores, 'mean', 0.95)
        {
            'statistic': 'mean',
            'estimate': 0.796,
            'ci_lower': 0.773,
            'ci_upper': 0.818,
            'confidence': 0.95
        }
    """
    if not sample:
        return {
            'statistic': statistic,
            'estimate': 0.0,
            'ci_lower': 0.0,
            'ci_upper': 0.0,
            'confidence': confidence
        }

    sample_array = np.array(sample)
    alpha = 1 - confidence

    # Calculate bootstrap samples
    bootstrap_statistics = []
    for _ in range(n_bootstrap):
        bootstrap_sample = np.random.choice(sample_array, size=len(sample_array), replace=True)

        if statistic == 'mean':
            stat_value = np.mean(bootstrap_sample)
        elif statistic == 'median':
            stat_value = np.median(bootstrap_sample)
        elif statistic == 'std':
            stat_value = np.std(bootstrap_sample, ddof=1)
        else:
            raise ValueError(f"Unknown statistic: {statistic}")

        bootstrap_statistics.append(stat_value)

    bootstrap_statistics = np.array(bootstrap_statistics)

    # Calculate confidence interval bounds
    ci_lower = np.percentile(bootstrap_statistics, 100 * alpha / 2)
    ci_upper = np.percentile(bootstrap_statistics, 100 * (1 - alpha / 2))

    # Calculate point estimate from original sample
    if statistic == 'mean':
        estimate = float(np.mean(sample_array))
    elif statistic == 'median':
        estimate = float(np.median(sample_array))
    elif statistic == 'std':
        estimate = float(np.std(sample_array, ddof=1))

    return {
        'statistic': statistic,
        'estimate': estimate,
        'ci_lower': float(ci_lower),
        'ci_upper': float(ci_upper),
        'confidence': confidence,
        'n_bootstrap': n_bootstrap
    }


def multiple_comparison_correction(
    p_values: List[float],
    method: str = 'bonferroni'
) -> List[float]:
    """
    Apply multiple comparison correction to p-values.

    Args:
        p_values: List of uncorrected p-values
        method: Correction method ('bonferroni' or 'holm')

    Returns:
        List of corrected p-values

    Example:
        >>> p_values = [0.01, 0.04, 0.03, 0.20]
        >>> multiple_comparison_correction(p_values, 'bonferroni')
        [0.04, 0.16, 0.12, 1.0]
    """
    n = len(p_values)

    if method == 'bonferroni':
        corrected = [min(p * n, 1.0) for p in p_values]
    elif method == 'holm':
        # Sort p-values with indices
        sorted_with_idx = sorted(enumerate(p_values), key=lambda x: x[1])
        corrected = [1.0] * n

        for rank, (idx, p) in enumerate(sorted_with_idx):
            corrected_p = p * (n - rank)
            corrected[idx] = min(corrected_p, 1.0)

        # Ensure monotonicity
        for i in range(1, n):
            orig_idx = sorted_with_idx[i][0]
            prev_idx = sorted_with_idx[i - 1][0]
            if corrected[orig_idx] < corrected[prev_idx]:
                corrected[orig_idx] = corrected[prev_idx]
    else:
        raise ValueError(f"Unknown correction method: {method}")

    return corrected


def calculate_effect_size(
    sample1: List[float],
    sample2: List[float],
    method: str = 'cohens_d'
) -> Dict[str, float]:
    """
    Calculate effect size between two samples.

    Effect size measures the magnitude of difference independent of sample size.

    Args:
        sample1: Metric values from algorithm 1
        sample2: Metric values from algorithm 2
        method: Effect size measure ('cohens_d' or 'glass_delta')

    Returns:
        Dictionary with effect size and interpretation

    Example:
        >>> algo1_scores = [0.8, 0.75, 0.82, 0.79, 0.81]
        >>> algo2_scores = [0.75, 0.73, 0.78, 0.76, 0.77]
        >>> calculate_effect_size(algo1_scores, algo2_scores)
        {
            'effect_size': 0.89,
            'interpretation': 'large effect',
            'method': 'cohens_d'
        }
    """
    mean1 = np.mean(sample1)
    mean2 = np.mean(sample2)

    if method == 'cohens_d':
        # Pooled standard deviation
        std1 = np.std(sample1, ddof=1) if len(sample1) > 1 else 0
        std2 = np.std(sample2, ddof=1) if len(sample2) > 1 else 0

        n1, n2 = len(sample1), len(sample2)
        pooled_std = np.sqrt(((n1 - 1) * std1**2 + (n2 - 1) * std2**2) / (n1 + n2 - 2))

        if pooled_std == 0:
            effect_size = 0.0
        else:
            effect_size = (mean1 - mean2) / pooled_std

    elif method == 'glass_delta':
        # Use std of control group (sample2)
        std2 = np.std(sample2, ddof=1) if len(sample2) > 1 else 0

        if std2 == 0:
            effect_size = 0.0
        else:
            effect_size = (mean1 - mean2) / std2
    else:
        raise ValueError(f"Unknown method: {method}")

    return {
        'effect_size': float(effect_size),
        'interpretation': _interpret_effect_size(abs(effect_size)),
        'method': method
    }


def _format_p_value_interpretation(p_value: float, alpha: float) -> str:
    """Format p-value interpretation string."""
    if p_value < 0.001:
        return f'Significant difference at alpha={alpha} (p < 0.001)'
    elif p_value < alpha:
        return f'Significant difference at alpha={alpha} (p={p_value:.4f})'
    else:
        return f'Not significant at alpha={alpha} (p={p_value:.4f})'


def _interpret_effect_size(effect_size: float) -> str:
    """Interpret effect size according to Cohen's conventions."""
    if effect_size < 0.2:
        return 'negligible effect'
    elif effect_size < 0.5:
        return 'small effect'
    elif effect_size < 0.8:
        return 'medium effect'
    else:
        return 'large effect'


def compare_algorithms(
    results: Dict[str, List[float]],
    alpha: float = 0.05
) -> Dict[str, Dict[str, Any]]:
    """
    Perform pairwise comparisons between all algorithms.

    Args:
        results: Dictionary mapping algorithm name to list of metric values
        alpha: Significance level

    Returns:
        Dictionary with pairwise comparison results

    Example:
        >>> results = {
        ...     'algo1': [0.8, 0.75, 0.82],
        ...     'algo2': [0.75, 0.73, 0.78],
        ...     'algo3': [0.70, 0.68, 0.72]
        ... }
        >>> compare_algorithms(results)
        {
            'algo1_vs_algo2': {'significant': True, 'p_value': 0.03, ...},
            'algo1_vs_algo3': {'significant': True, 'p_value': 0.01, ...},
            'algo2_vs_algo3': {'significant': False, 'p_value': 0.15, ...}
        }
    """
    algo_names = list(results.keys())
    comparisons = {}

    for i in range(len(algo_names)):
        for j in range(i + 1, len(algo_names)):
            name1, name2 = algo_names[i], algo_names[j]
            comparison_key = f'{name1}_vs_{name2}'

            # Run statistical tests
            ttest_result = paired_ttest(results[name1], results[name2], alpha)
            wilcoxon_result = wilcoxon_signed_rank_test(results[name1], results[name2], alpha)
            effect_size_result = calculate_effect_size(results[name1], results[name2])

            comparisons[comparison_key] = {
                't_test': ttest_result,
                'wilcoxon': wilcoxon_result,
                'effect_size': effect_size_result,
                'mean_difference': np.mean(results[name1]) - np.mean(results[name2])
            }

    return comparisons
