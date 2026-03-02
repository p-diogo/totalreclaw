#!/usr/bin/env python3
"""
TotalReclaw Testbed - Main CLI Entry Point

Run complete search algorithm evaluation:
  python run_evaluation.py --config config/evaluation.yaml

Or run specific components:
  python run_evaluation.py generate-queries --output data/queries/
  python run_evaluation.py labeling-interface --port 5000
  python run_evaluation.py evaluate --results data/results/
"""

import argparse
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.queries import QueryGenerator
from src.labeling import LabelingInterface, export_labels, import_labels, merge_evaluator_labels
from src.evaluation import SearchEvaluator, EvaluationConfig, EvaluationResults
from src.evaluation import ReportGenerator, GoNoGoDecision, DecisionCriteria


def cmd_generate_queries(args):
    """Generate test queries."""
    print("Generating test queries...")

    generator = QueryGenerator(seed=args.seed)

    if args.dataset:
        # Load documents for dataset-aware generation
        print(f"Loading documents from {args.dataset}...")
        # TODO: Implement document loading
        queries = generator.generate(num_queries=args.count)
    else:
        queries = generator.generate(num_queries=args.count)

    # Save queries
    import json
    os.makedirs(args.output, exist_ok=True)
    output_path = os.path.join(args.output, 'test_queries.json')

    with open(output_path, 'w') as f:
        json.dump(queries, f, indent=2)

    print(f"Generated {len(queries)} queries")
    print(f"Saved to {output_path}")

    # Print distribution
    from collections import Counter
    distribution = Counter(q['category'] for q in queries)
    print("\nQuery distribution:")
    for category, count in distribution.items():
        print(f"  {category}: {count} ({count/len(queries)*100:.1f}%)")


def cmd_labeling_interface(args):
    """Start the web-based labeling interface."""
    print(f"Starting labeling interface on port {args.port}...")

    # Load queries
    import json
    queries_path = args.queries or 'data/queries/test_queries.json'
    with open(queries_path, 'r') as f:
        queries = json.load(f)

    # Load documents
    # TODO: Implement document loading from database or files
    documents = {}  # doc_id -> text

    # Create evaluator IDs
    evaluator_ids = [f'eval{i+1}' for i in range(args.evaluators)]

    # Start interface
    interface = LabelingInterface(
        queries=queries,
        documents=documents,
        evaluator_ids=evaluator_ids,
        output_dir=args.output_dir
    )

    interface.run(host=args.host, port=args.port)


def cmd_merge_labels(args):
    """Merge labels from multiple evaluators."""
    print("Merging evaluator labels...")

    all_labels = []
    for evaluator_id in args.evaluators:
        label_path = os.path.join(args.input_dir, f'labels_{evaluator_id}.json')
        labels = import_labels(label_path)
        all_labels.append(labels)
        print(f"  Loaded {len(labels)} labels from {evaluator_id}")

    # Merge using majority voting
    ground_truth = merge_evaluator_labels(all_labels, num_evaluators=len(args.evaluators))

    # Export ground truth
    import json
    output_path = os.path.join(args.input_dir, 'ground_truth.json')
    with open(output_path, 'w') as f:
        json.dump(ground_truth, f, indent=2)

    print(f"\nGround truth saved to {output_path}")
    print(f"Total queries: {len(ground_truth)}")


def cmd_evaluate(args):
    """Run search algorithm evaluation."""
    print("Running search algorithm evaluation...")

    # Load configuration
    import yaml
    with open(args.config, 'r') as f:
        config = yaml.safe_load(f)

    # Load queries
    import json
    queries_path = args.queries or os.path.join(args.data_dir, 'queries/test_queries.json')
    with open(queries_path, 'r') as f:
        queries = json.load(f)

    # Load ground truth
    gt_path = args.ground_truth or os.path.join(args.data_dir, 'ground_truth/ground_truth.json')
    with open(gt_path, 'r') as f:
        ground_truth = json.load(f)

    # Load documents
    # TODO: Implement document loading
    documents = []
    document_ids = list(range(len(documents)))

    # Load algorithms
    algorithms = {}
    for algo_config in config.get('algorithms', []):
        algo_name = algo_config['name']
        # TODO: Import and instantiate algorithm
        print(f"Loading algorithm: {algo_name}")

    # Create evaluation config
    eval_config = EvaluationConfig(
        documents=documents,
        document_ids=document_ids,
        ground_truth=ground_truth,
        queries=queries,
        algorithms=algorithms,
        top_k=config['evaluation']['top_k']
    )

    # Run evaluation
    evaluator = SearchEvaluator(eval_config)
    results = evaluator.run_evaluation()

    # Generate report
    generator = ReportGenerator()

    # Go/No-Go decision
    go_no_go_framework = GoNoGoDecision(DecisionCriteria())
    go_no_go_result = go_no_go_framework.evaluate(
        results={name: result.to_dict() for name, result in results.algorithm_results.items()},
        totalreclaw_algo='totalreclaw_v05',
        baseline_algo='qmd_hybrid'
    )

    # Generate reports
    report_path = generator.generate(
        results,
        go_no_go_result,
        output_dir=args.output_dir
    )

    print(f"\nEvaluation complete!")
    print(f"Report saved to: {report_path}")
    print(f"\nDecision: {go_no_go_result.decision.value}")


def cmd_report(args):
    """Generate report from existing results."""
    print("Generating report from existing results...")

    # Load results
    results = EvaluationResults.from_json(args.results)

    # Generate report
    generator = ReportGenerator()
    report_path = generator.generate(
        results,
        output_dir=args.output_dir
    )

    print(f"Report saved to: {report_path}")


def main():
    parser = argparse.ArgumentParser(
        description='TotalReclaw Testbed - Search Algorithm Evaluation Framework',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate test queries
  python run_evaluation.py generate-queries --count 150 --output data/queries/

  # Start labeling interface
  python run_evaluation.py labeling-interface --queries data/queries/test_queries.json

  # Merge labels from evaluators
  python run_evaluation.py merge-labels --evaluators eval1 eval2 eval3

  # Run full evaluation
  python run_evaluation.py evaluate --config config/evaluation.yaml

  # Generate report from results
  python run_evaluation.py report --results data/results/evaluation_results.json
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # generate-queries command
    parser_generate = subparsers.add_parser('generate-queries', help='Generate test queries')
    parser_generate.add_argument('--count', type=int, default=150, help='Number of queries to generate')
    parser_generate.add_argument('--output', type=str, default='data/queries/', help='Output directory')
    parser_generate.add_argument('--dataset', type=str, help='Path to dataset for dataset-aware generation')
    parser_generate.add_argument('--seed', type=int, default=42, help='Random seed')

    # labeling-interface command
    parser_labeling = subparsers.add_parser('labeling-interface', help='Start web labeling interface')
    parser_labeling.add_argument('--queries', type=str, help='Path to queries JSON file')
    parser_labeling.add_argument('--evaluators', type=int, default=3, help='Number of evaluators')
    parser_labeling.add_argument('--host', type=str, default='0.0.0.0', help='Host to bind to')
    parser_labeling.add_argument('--port', type=int, default=5000, help='Port to bind to')
    parser_labeling.add_argument('--output-dir', type=str, default='data/ground_truth/', help='Output directory for labels')

    # merge-labels command
    parser_merge = subparsers.add_parser('merge-labels', help='Merge labels from multiple evaluators')
    parser_merge.add_argument('--evaluators', nargs='+', default=['eval1', 'eval2', 'eval3'], help='Evaluator IDs')
    parser_merge.add_argument('--input-dir', type=str, default='data/ground_truth/', help='Input directory for label files')

    # evaluate command
    parser_eval = subparsers.add_parser('evaluate', help='Run search algorithm evaluation')
    parser_eval.add_argument('--config', type=str, default='config/evaluation.yaml', help='Configuration file')
    parser_eval.add_argument('--data-dir', type=str, default='data/', help='Data directory')
    parser_eval.add_argument('--queries', type=str, help='Path to queries JSON file')
    parser_eval.add_argument('--ground-truth', type=str, help='Path to ground truth JSON file')
    parser_eval.add_argument('--output-dir', type=str, default='reports/', help='Output directory for reports')

    # report command
    parser_report = subparsers.add_parser('report', help='Generate report from existing results')
    parser_report.add_argument('--results', type=str, required=True, help='Path to results JSON file')
    parser_report.add_argument('--output-dir', type=str, default='reports/', help='Output directory for reports')

    args = parser.parse_args()

    if args.command == 'generate-queries':
        cmd_generate_queries(args)
    elif args.command == 'labeling-interface':
        cmd_labeling_interface(args)
    elif args.command == 'merge-labels':
        cmd_merge_labels(args)
    elif args.command == 'evaluate':
        cmd_evaluate(args)
    elif args.command == 'report':
        cmd_report(args)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
