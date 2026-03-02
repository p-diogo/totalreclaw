"""
Latency metrics for measuring search performance.

Calculates percentiles (p50, p95, p99) and statistics.
"""

from typing import List, Tuple
import numpy as np
import statistics


def calculate_percentile(values: List[float], percentile: float) -> float:
    """
    Calculate a specific percentile of a list of values.

    Args:
        values: List of numeric values (latencies in milliseconds)
        percentile: Percentile to calculate (0-100)

    Returns:
        Value at the specified percentile

    Example:
        >>> latencies = [100, 150, 200, 250, 300, 350, 400]
        >>> calculate_percentile(latencies, 95)
        385.0
    """
    if not values:
        return 0.0

    return float(np.percentile(values, percentile))


def calculate_latency_percentiles(
    latencies: List[float],
    percentiles: List[float] = None
) -> dict:
    """
    Calculate multiple latency percentiles.

    Args:
        latencies: List of latency values in milliseconds
        percentiles: List of percentiles to calculate (default: [50, 95, 99])

    Returns:
        Dictionary mapping percentile name to value

    Example:
        >>> latencies = [100, 150, 200, 250, 300, 350, 400]
        >>> calculate_latency_percentiles(latencies)
        {'p50': 250.0, 'p95': 385.0, 'p99': 394.0}
    """
    if percentiles is None:
        percentiles = [50, 95, 99]

    result = {}
    for p in percentiles:
        result[f'p{p}'] = calculate_percentile(latencies, p)

    return result


def calculate_latency_statistics(latencies: List[float]) -> dict:
    """
    Calculate comprehensive latency statistics.

    Args:
        latencies: List of latency values in milliseconds

    Returns:
        Dictionary with min, max, mean, median, std, p50, p95, p99

    Example:
        >>> latencies = [100, 150, 200, 250, 300, 350, 400]
        >>> calculate_latency_statistics(latencies)
        {
            'min': 100.0, 'max': 400.0, 'mean': 250.0,
            'median': 250.0, 'std': 111.8, 'p50': 250.0,
            'p95': 385.0, 'p99': 394.0
        }
    """
    if not latencies:
        return {
            'min': 0.0, 'max': 0.0, 'mean': 0.0,
            'median': 0.0, 'std': 0.0, 'p50': 0.0,
            'p95': 0.0, 'p99': 0.0, 'count': 0
        }

    percentiles = calculate_latency_percentiles(latencies, [50, 95, 99])

    return {
        'min': float(min(latencies)),
        'max': float(max(latencies)),
        'mean': float(statistics.mean(latencies)),
        'median': float(statistics.median(latencies)),
        'std': float(statistics.stdev(latencies)) if len(latencies) > 1 else 0.0,
        'count': len(latencies),
        **percentiles
    }


def calculate_throughput(
    total_queries: int,
    total_time_seconds: float
) -> dict:
    """
    Calculate throughput metrics.

    Args:
        total_queries: Number of queries executed
        total_time_seconds: Total time elapsed in seconds

    Returns:
        Dictionary with queries per second and average latency

    Example:
        >>> calculate_throughput(1000, 10.0)
        {'qps': 100.0, 'avg_latency_ms': 10.0}
    """
    if total_time_seconds == 0:
        return {'qps': 0.0, 'avg_latency_ms': 0.0}

    qps = total_queries / total_time_seconds
    avg_latency_ms = (total_time_seconds / total_queries) * 1000

    return {
        'qps': qps,
        'avg_latency_ms': avg_latency_ms
    }


def classify_latency(latency_ms: float, thresholds: dict = None) -> str:
    """
    Classify latency into performance category.

    Args:
        latency_ms: Latency value in milliseconds
        thresholds: Dictionary with threshold values

    Returns:
        Performance category: 'excellent', 'good', 'fair', 'poor'

    Example:
        >>> classify_latency(150)
        'excellent'
        >>> classify_latency(1200)
        'fair'
    """
    if thresholds is None:
        # Default thresholds based on TotalReclaw targets
        thresholds = {
            'excellent': 500,   # < 500ms
            'good': 1000,       # < 1s
            'fair': 1500,       # < 1.5s
        }

    if latency_ms < thresholds.get('excellent', 500):
        return 'excellent'
    elif latency_ms < thresholds.get('good', 1000):
        return 'good'
    elif latency_ms < thresholds.get('fair', 1500):
        return 'fair'
    else:
        return 'poor'


def calculate_latency_distribution(
    latencies: List[float],
    bin_size_ms: int = 100
) -> List[Tuple[str, int]]:
    """
    Calculate latency distribution histogram.

    Args:
        latencies: List of latency values in milliseconds
        bin_size_ms: Size of each histogram bin in milliseconds

    Returns:
        List of (bin_label, count) tuples

    Example:
        >>> latencies = [100, 150, 200, 250, 300, 350, 400, 800]
        >>> calculate_latency_distribution(latencies, 200)
        [('0-200', 2), ('200-400', 4), ('400-600', 0), ('600-800', 1), ('800+', 1)]
    """
    if not latencies:
        return []

    max_latency = max(latencies)
    num_bins = int((max_latency / bin_size_ms)) + 1

    distribution = []
    for i in range(num_bins + 1):
        bin_start = i * bin_size_ms
        bin_end = (i + 1) * bin_size_ms

        if i == num_bins:
            # Last bin for overflow
            label = f'{bin_start}+'
            count = sum(1 for l in latencies if l >= bin_start)
        else:
            label = f'{bin_start}-{bin_end}'
            count = sum(1 for l in latencies if bin_start <= l < bin_end)

        if count > 0 or i == num_bins:
            distribution.append((label, count))

    return distribution
