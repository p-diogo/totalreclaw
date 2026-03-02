#!/usr/bin/env python3
"""
Master Runner Script - TotalReclaw v1.0 Testbed Evaluation

This script executes all evaluation scenarios in sequence:
- S1-S4: Baseline algorithms (BM25, Vector, OpenClaw, QMD)
- S5: TotalReclaw v0.2 E2EE
- S6-S7: TotalReclaw v0.5 E2EE (with and without LLM)
- S8: LLM Rerank Isolation Benchmark
- Final: Generate comprehensive report

Provides progress tracking, error handling, and execution summary.

Usage:
    cd testbed/v1.0-llm-gt-comparison
    python scripts/run_all.py
"""

import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple
from datetime import datetime


# Script execution order
SCRIPTS = [
    {
        "name": "Baseline Algorithms (S1-S4)",
        "script": "01_run_baselines.py",
        "description": "BM25-Only, Vector-Only, OpenClaw Hybrid, QMD Hybrid",
        "output": "results/baselines.json",
    },
    {
        "name": "TotalReclaw v0.2 E2EE (S5)",
        "script": "02_run_totalreclaw_v02.py",
        "description": "Two-pass search with real AES-GCM encryption",
        "output": "results/totalreclaw_v02.json",
    },
    {
        "name": "TotalReclaw v0.5 E2EE (S6-S7)",
        "script": "03_run_totalreclaw_v05.py",
        "description": "Three-pass with and without LLM reranking",
        "output": "results/totalreclaw_v05.json",
    },
    {
        "name": "LLM Rerank Benchmark (S8)",
        "script": "04_benchmark_llm_rerank.py",
        "description": "LLM reranking bottleneck isolation test",
        "output": "results/llm_rerank_benchmark.json",
    },
    {
        "name": "Generate Final Report",
        "script": "05_generate_report.py",
        "description": "Comprehensive evaluation report with Go/No-Go decision",
        "output": "reports/EVALUATION_REPORT.md",
    },
]


class ScriptRunner:
    """Runner for executing all testbed scripts."""

    def __init__(self, scripts_dir: Path):
        self.scripts_dir = scripts_dir
        self.results: Dict[str, Dict] = {}
        self.start_time = time.time()

    def print_header(self):
        """Print execution header."""
        print("=" * 80)
        print("TotalReclaw v1.0 Testbed - Master Runner")
        print("=" * 80)
        print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Working Directory: {self.scripts_dir.parent}")
        print(f"Scripts Directory: {self.scripts_dir}")
        print("=" * 80)
        print()
        print("Execution Plan:")
        for i, script in enumerate(SCRIPTS, 1):
            print(f"  {i}. {script['name']}")
            print(f"     -> {script['description']}")
            print(f"     -> Output: {script['output']}")
        print()
        print("=" * 80)
        print()

    def run_script(self, script_info: Dict) -> Tuple[bool, str, float]:
        """
        Run a single script.

        Returns:
            (success, error_message, elapsed_time)
        """
        script_path = self.scripts_dir / script_info["script"]

        if not script_path.exists():
            return False, f"Script not found: {script_path}", 0.0

        print(f"\n{'=' * 80}")
        print(f"Running: {script_info['name']}")
        print(f"Script: {script_info['script']}")
        print(f"{'=' * 80}\n")

        start = time.time()

        try:
            # Run the script and capture output
            result = subprocess.run(
                [sys.executable, str(script_path)],
                cwd=str(self.scripts_dir.parent),
                capture_output=True,
                text=True,
                timeout=3600,  # 1 hour timeout per script
            )

            elapsed = time.time() - start

            # Print output
            if result.stdout:
                print(result.stdout)

            if result.returncode != 0:
                if result.stderr:
                    print(f"\nERROR OUTPUT:\n{result.stderr}", file=sys.stderr)
                return False, f"Script failed with exit code {result.returncode}", elapsed

            return True, "", elapsed

        except subprocess.TimeoutExpired:
            return False, "Script execution timed out (1 hour limit)", time.time() - start
        except Exception as e:
            return False, f"Exception: {e}", time.time() - start

    def check_output_file(self, output_path: str) -> bool:
        """Check if the output file exists."""
        output = self.scripts_dir.parent / output_path
        return output.exists()

    def run_all(self) -> bool:
        """
        Run all scripts in sequence.

        Returns:
            True if all scripts succeeded, False otherwise
        """
        self.print_header()

        total_scripts = len(SCRIPTS)

        for i, script_info in enumerate(SCRIPTS, 1):
            script_name = script_info["name"]
            script_file = script_info["script"]

            print(f"\n[{i}/{total_scripts}] Starting: {script_name}")
            print(f"Timestamp: {datetime.now().strftime('%H:%M:%S')}")

            # Run the script
            success, error, elapsed = self.run_script(script_info)

            # Store result
            self.results[script_name] = {
                "success": success,
                "error": error,
                "elapsed_time": elapsed,
                "output_exists": self.check_output_file(script_info["output"]),
                "output_file": script_info["output"],
            }

            # Report result
            if success:
                print(f"\n[SUCCESS] {script_name} completed in {elapsed:.1f} seconds")
                output_exists = self.results[script_name]["output_exists"]
                if output_exists:
                    print(f"[SUCCESS] Output file created: {script_info['output']}")
                else:
                    print(f"[WARNING] Expected output file not found: {script_info['output']}")
            else:
                print(f"\n[FAILED] {script_name}: {error}")
                print(f"[INFO] Continuing with remaining scripts...")

        return all(r["success"] for r in self.results.values())

    def print_summary(self):
        """Print execution summary."""
        total_elapsed = time.time() - self.start_time

        print("\n")
        print("=" * 80)
        print("EXECUTION SUMMARY")
        print("=" * 80)
        print(f"Total Time: {total_elapsed:.1f} seconds ({total_elapsed/60:.1f} minutes)")
        print(f"Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()
        print("Script Status:")
        print("-" * 80)

        for script_name, result in self.results.items():
            status = "SUCCESS" if result["success"] else "FAILED"
            elapsed = result["elapsed_time"]
            output = result["output_file"]

            print(f"\n{script_name}:")
            print(f"  Status:    {status}")
            print(f"  Time:      {elapsed:.1f}s")
            print(f"  Output:    {output}")
            print(f"  Generated: {'Yes' if result['output_exists'] else 'No'}")

            if not result["success"] and result["error"]:
                print(f"  Error:     {result['error']}")

        print()
        print("-" * 80)

        # Count successes/failures
        successes = sum(1 for r in self.results.values() if r["success"])
        failures = len(self.results) - successes

        print(f"\nTotal: {len(self.results)} scripts")
        print(f"  Successes: {successes}")
        print(f"  Failures:  {failures}")

        # Final report location
        report_script = SCRIPTS[-1]  # Generate report is last
        if self.results.get(report_script["name"], {}).get("output_exists"):
            reports_dir = self.scripts_dir.parent / "reports"
            md_report = reports_dir / "EVALUATION_REPORT.md"
            html_report = reports_dir / "EXECUTIVE_SUMMARY.html"

            print()
            print("Final Report Location:")
            print(f"  Markdown: {md_report}")
            print(f"  HTML:     {html_report}")

        print()
        print("=" * 80)

        # Return exit code
        if failures > 0:
            print("\nSome scripts failed. Please check the errors above.")
            return 1
        else:
            print("\nAll scripts completed successfully!")
            return 0


def main():
    """Main entry point."""

    # Determine scripts directory
    # This script should be in testbed/v1.0-llm-gt-comparison/scripts/
    script_file = Path(__file__).resolve()
    scripts_dir = script_file.parent

    # Verify we're in the right place
    if scripts_dir.name != "scripts":
        print(f"Error: Script must be in 'scripts' directory, found: {scripts_dir}")
        sys.exit(1)

    # Create runner and execute
    runner = ScriptRunner(scripts_dir)
    all_success = runner.run_all()

    # Print summary and exit
    exit_code = runner.print_summary()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
