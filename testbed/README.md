# TotalReclaw Testbed - Evaluation Framework

Comprehensive evaluation framework for benchmarking search algorithm accuracy in the TotalReclaw zero-knowledge E2EE testbed.

## Overview

This framework provides:

1. **Metrics Calculation Module**
   - Precision, Recall, F1 Score
   - Mean Reciprocal Rank (MRR)
   - Mean Average Precision (MAP)
   - NDCG (Normalized Discounted Cumulative Gain)
   - Latency percentiles (p50, p95, p99)

2. **Ground Truth Labeling System**
   - Web-based labeling interface (Flask)
   - Support for 3 independent evaluators
   - Majority voting for disagreements
   - Fleiss' kappa for inter-annotator agreement

3. **Test Query Generator**
   - 150 queries across 6 categories
   - Contextual/Fact Retrieval: 45 (30%)
   - Configuration & Setup: 30 (20%)
   - Temporal/Recent Activity: 22 (15%)
   - Error & Solution Lookup: 22 (15%)
   - Semantic/Concept: 18 (12%)
   - Exact/Keyword: 13 (8%)

4. **Comprehensive Report Generator**
   - Comparison tables (all algorithms × all metrics)
   - Performance by query category
   - Statistical significance tests
   - Visualization charts
   - Go/No-Go recommendation

## Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Or using uv
uv pip install -r requirements.txt
```

## Quick Start

### 1. Generate Test Queries

```bash
python run_evaluation.py generate-queries --count 150 --output data/queries/
```

### 2. Start Labeling Interface

```bash
python run_evaluation.py labeling-interface --queries data/queries/test_queries.json --port 5000
```

Then open http://localhost:5000 in your browser.

### 3. Merge Labels from Evaluators

```bash
python run_evaluation.py merge-labels --evaluators eval1 eval2 eval3
```

### 4. Run Evaluation

```bash
python run_evaluation.py evaluate --config config/evaluation.yaml
```

### 5. Generate Report

```bash
python run_evaluation.py report --results data/results/evaluation_results.json
```

## Module Reference

### Metrics Module

```python
from src.metrics import (
    calculate_precision,
    calculate_recall,
    calculate_f1,
    calculate_mrr,
    calculate_fleiss_kappa
)

# Basic usage
retrieved = {1, 2, 3, 4, 5}
relevant = {1, 3, 5, 7, 9}

precision = calculate_precision(retrieved, relevant)  # 0.6
recall = calculate_recall(retrieved, relevant)        # 0.6
f1 = calculate_f1(retrieved, relevant)               # 0.6
```

### Query Generator

```python
from src.queries import QueryGenerator

generator = QueryGenerator(seed=42)
queries = generator.generate(num_queries=150)

# Or generate queries tailored to your dataset
queries = generator.generate_for_dataset(documents, num_queries=150)
```

### Evaluation Framework

```python
from src.evaluation import SearchEvaluator, EvaluationConfig

config = EvaluationConfig(
    documents=documents,
    document_ids=list(range(len(documents))),
    ground_truth=ground_truth,
    queries=queries,
    algorithms={
        'bm25': bm25_search,
        'vector': vector_search,
        'hybrid': hybrid_search
    }
)

evaluator = SearchEvaluator(config)
results = evaluator.run_evaluation()
```

### Go/No-Go Decision

```python
from src.evaluation import GoNoGoDecision, DecisionCriteria

framework = GoNoGoDecision(DecisionCriteria())
result = framework.evaluate(
    results=algorithm_results,
    totalreclaw_algo='totalreclaw_v05',
    baseline_algo='qmd_hybrid'
)

print(result.decision)  # Decision.GO, Decision.MODIFY, or Decision.NO_GO
print(result.rationale)
```

## Configuration

Edit `config/evaluation.yaml` to customize:

- Dataset size and chunking parameters
- Query distribution
- Algorithm configurations
- Go/No-Go thresholds
- Output settings

## Output

The evaluation generates:

1. **JSON Results** (`evaluation_results_*.json`)
   - Complete per-query results
   - Algorithm aggregates
   - Statistical comparisons

2. **Markdown Report** (`evaluation_report_*.md`)
   - Executive summary
   - Comparison tables
   - Category breakdowns
   - Go/No-Go recommendation

3. **Charts** (`evaluation_charts_*.png`)
   - Metric comparison bar charts
   - Latency distributions
   - Per-category performance

## Go/No-Go Criteria

### GO (Proceed to Development)
- F1 score > 0.80 OR
- Within 5% of baseline F1 score OR
- MRR > 0.70 with recall > 0.75
- AND OpenClaw compatibility met

### MODIFY (Adjust Architecture)
- F1 score 0.75-0.80 OR
- Within 10% of baseline with clear gaps
- MRR 0.65-0.70
- OR OpenClaw compatibility needs work (fixable)

### NO-GO (Reconsider Architecture)
- F1 score < 0.75 OR
- > 15% gap from baseline
- MRR < 0.65
- OR OpenClaw compatibility fundamentally broken

## License

MIT License - See LICENSE file for details.
