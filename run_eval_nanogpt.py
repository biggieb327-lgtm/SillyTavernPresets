#!/usr/bin/env python3
"""
Evaluation runner for GLM and Gemma models via NanoGPT API.
Uses lm-evaluation-harness with local-completions model.
"""
import os
import sys
import json
import argparse
import subprocess
from pathlib import Path
from datetime import datetime

# Models available on NanoGPT
MODELS = {
    "glm-4.7": "zai-org/glm-4.7",
    "gemma-4-31b": "google/gemma-4-31b-it",
    "gemma-3-27b": "google/gemma-3-27b-it",
    "gemma-3-12b": "google/gemma-3-12b-it",
    "gemma-3-4b": "google/gemma-3-4b-it",
    "gemma-3-1b": "google/gemma-3-1b-it",
}

# Tasks that work with generate_until (no logprobs needed)
GENERATE_TASKS = [
    "gsm8k",
    "hellaswag", 
    "arc_easy",
    "arc_challenge",
    "truthfulqa_gen",
    "bbh",
    "gpqa",
    "humaneval",
    "mbpp",
    "math",
    "drop",
    "boolq",
    "piqa",
    "winogrande",
    "siqa",
    "race",
    "logiqa",
    "xstorycloze",
]

# Tasks needing loglikelihood (require logprobs - may not work)
LOGLIKELIHOOD_TASKS = [
    "mmlu",
    "truthfulqa_mc1",
    "truthfulqa_mc2",
]

def run_eval(model_name, model_id, tasks, limit=None, output_dir=None):
    """Run lm-eval for a model on specified tasks."""
    if output_dir is None:
        output_dir = Path("eval_results") / f"{model_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    api_key = os.environ.get("NANOGPT_API_KEY")
    if not api_key:
        print("Error: NANOGPT_API_KEY environment variable not set")
        return None
    
    model_args = json.dumps({
        "model": model_id,
        "base_url": "https://nano-gpt.com/api/v1/completions",
        "header": {"Authorization": f"Bearer {api_key}"},
        "tokenizer_backend": "huggingface",
    })
    
    task_list = ",".join(tasks)
    cmd = [
        "lm-eval",
        "--model", "local-completions",
        "--model_args", model_args,
        "--tasks", task_list,
        "--output_path", str(output_dir),
    ]
    
    if limit:
        cmd.extend(["--limit", str(limit)])
    
    print(f"\n{'='*60}")
    print(f"Running evaluation: {model_name} ({model_id})")
    print(f"Tasks: {task_list}")
    print(f"Limit: {limit or 'None (full)'}")
    print(f"Output: {output_dir}")
    print(f"{'='*60}\n")
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        
        # Check for results file
        result_files = list(output_dir.glob("*.json"))
        if result_files:
            with open(result_files[0]) as f:
                data = json.load(f)
            return data
        return None
    except subprocess.TimeoutExpired:
        print(f"Evaluation timed out for {model_name}")
        return None
    except Exception as e:
        print(f"Error running evaluation: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description="Run evaluations via NanoGPT")
    parser.add_argument("--models", nargs="+", choices=list(MODELS.keys()), 
                        default=["glm-4.7", "gemma-4-31b"],
                        help="Models to evaluate")
    parser.add_argument("--tasks", nargs="+", default=["gsm8k", "hellaswag", "arc_easy", "arc_challenge"],
                        help="Tasks to run")
    parser.add_argument("--limit", type=int, default=None,
                        help="Limit samples per task (for testing)")
    parser.add_argument("--list", action="store_true", help="List available models")
    parser.add_argument("--list-tasks", action="store_true", help="List available tasks")
    args = parser.parse_args()
    
    if args.list:
        print("Available models:")
        for name, model_id in MODELS.items():
            print(f"  {name}: {model_id}")
        return
    
    if args.list_tasks:
        print("Generate-until tasks (work without logprobs):")
        for t in GENERATE_TASKS:
            print(f"  {t}")
        print("\nLoglikelihood tasks (need logprobs - may fail):")
        for t in LOGLIKELIHOOD_TASKS:
            print(f"  {t}")
        return
    
    api_key = os.environ.get("NANOGPT_API_KEY")
    if not api_key:
        print("Error: Set NANOGPT_API_KEY environment variable")
        sys.exit(1)
    
    print(f"API Key: {api_key[:10]}...")
    
    # Run evaluations
    all_results = {}
    for model_name in args.models:
        model_id = MODELS[model_name]
        results = run_eval(model_name, model_id, args.tasks, args.limit)
        if results:
            all_results[model_name] = results
    
    # Generate comparison report
    if all_results:
        report_path = Path("eval_results") / f"REPORT_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(report_path, "w") as f:
            f.write("# Model Evaluation Report\n\n")
            f.write(f"Generated: {datetime.now().isoformat()}\n\n")
            f.write(f"API: NanoGPT (nano-gpt.com)\n\n")
            
            for model_name, results in all_results.items():
                f.write(f"\n## {model_name}\n\n")
                if "results" in results:
                    for task, metrics in results["results"].items():
                        f.write(f"### {task}\n")
                        for metric, value in metrics.items():
                            if isinstance(value, dict):
                                f.write(f"  {metric}: {value}\n")
                            else:
                                f.write(f"  {metric}: {value}\n")
                        f.write("\n")
        
        print(f"\nReport saved to: {report_path}")

if __name__ == "__main__":
    main()
