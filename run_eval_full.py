#!/usr/bin/env python3
"""
Full automated evaluation runner for GLM and Gemma models.
Supports multiple model backends and generates comparison reports.
"""

import subprocess
import json
import os
import sys
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any

class ModelEvaluator:
    def __init__(self, output_base: Path):
        self.output_base = output_base
        self.output_base.mkdir(exist_ok=True)
        self.results = {}
        self.tasks = [
            'mmlu', 'gsm8k', 'hellaswag', 
            'arc_easy', 'arc_challenge', 'truthfulqa'
        ]
        
    def run_command(self, cmd: List[str], timeout: int = 3600) -> Dict:
        """Run a command and return structured result."""
        print(f"  $ {' '.join(cmd)}")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            return {
                'command': ' '.join(cmd),
                'exit_code': result.returncode,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'success': result.returncode == 0
            }
        except subprocess.TimeoutExpired:
            return {
                'command': ' '.join(cmd),
                'exit_code': -1,
                'stdout': '',
                'stderr': f'Timeout after {timeout}s',
                'success': False
            }
        except Exception as e:
            return {
                'command': ' '.join(cmd),
                'exit_code': -1,
                'stdout': '',
                'stderr': str(e),
                'success': False
            }
    
    def parse_results(self, stdout: str) -> Dict:
        """Parse lm-eval output for key metrics."""
        metrics = {}
        for line in stdout.split('\n'):
            if '|' in line and any(m in line for m in ['acc', 'em', 'f1', 'bleu', 'rouge']):
                parts = [p.strip() for p in line.split('|')]
                if len(parts) >= 7:
                    task = parts[1].strip()
                    metric = parts[4].strip()
                    value_str = parts[5].strip()
                    try:
                        value = float(value_str)
                        if task not in metrics:
                            metrics[task] = {}
                        metrics[task][metric] = value
                    except ValueError:
                        pass
        return metrics
    
    def evaluate_model(self, name: str, model_type: str, model_args: str, 
                       apply_chat_template: bool = False, 
                       fewshot_as_multiturn: bool = False,
                       limit: Optional[int] = None,
                       batch_size: str = "auto") -> Dict:
        """Evaluate a single model configuration."""
        
        print(f"\n{'='*60}")
        print(f"Evaluating: {name}")
        print(f"  Model: {model_type} ({model_args})")
        print(f"  Tasks: {', '.join(self.tasks)}")
        if limit:
            print(f"  Limit: {limit} samples per task")
        print(f"{'='*60}")
        
        output_dir = self.output_base / name.replace('/', '-').replace(' ', '_')
        output_dir.mkdir(exist_ok=True)
        
        cmd = [
            'lm-eval', 'run',
            '--model', model_type,
            '--model_args', model_args,
            '--tasks', ','.join(self.tasks),
            '--output_path', str(output_dir),
            '--batch_size', batch_size,
        ]
        
        if limit:
            cmd.extend(['--limit', str(limit)])
        if apply_chat_template:
            cmd.append('--apply_chat_template')
        if fewshot_as_multiturn:
            cmd.append('--fewshot_as_multiturn')
        
        start_time = time.time()
        result = self.run_command(cmd)
        elapsed = time.time() - start_time
        
        result['elapsed_seconds'] = elapsed
        result['model_name'] = name
        result['model_type'] = model_type
        result['model_args'] = model_args
        
        if result['success']:
            result['metrics'] = self.parse_results(result['stdout'])
            print(f"  ✓ Completed in {elapsed:.1f}s")
            for task, metrics in result['metrics'].items():
                for metric, value in metrics.items():
                    print(f"    {task}/{metric}: {value:.4f}")
        else:
            result['metrics'] = {}
            print(f"  ✗ Failed after {elapsed:.1f}s")
            print(f"    Error: {result['stderr'][:300]}")
        
        # Save individual result
        with open(output_dir / 'result.json', 'w') as f:
            json.dump(result, f, indent=2)
        
        self.results[name] = result
        return result
    
    def generate_report(self) -> str:
        """Generate a comparison report."""
        report_lines = [
            "# Model Evaluation Report",
            f"Generated: {datetime.now().isoformat()}",
            f"Tasks: {', '.join(self.tasks)}",
            "",
            "## Summary",
            ""
        ]
        
        # Create comparison table
        if self.results:
            report_lines.append("| Model | MMLU | GSM8K | HellaSwag | ARC-Easy | ARC-Challenge | TruthfulQA MC1 |")
            report_lines.append("|-------|------|-------|-----------|----------|---------------|----------------|")
            
            for name, result in self.results.items():
                if result['success'] and result['metrics']:
                    m = result['metrics']
                    mmlu = m.get('mmlu', {}).get('acc', 'N/A')
                    gsm8k = m.get('gsm8k', {}).get('exact_match', 'N/A')
                    hellaswag = m.get('hellaswag', {}).get('acc_norm', 'N/A')
                    arc_easy = m.get('arc_easy', {}).get('acc', 'N/A')
                    arc_challenge = m.get('arc_challenge', {}).get('acc', 'N/A')
                    truthfulqa = m.get('truthfulqa_mc1', {}).get('acc', 'N/A')
                    
                    def fmt(v):
                        return f"{v:.3f}" if isinstance(v, float) else str(v)
                    
                    report_lines.append(
                        f"| {name} | {fmt(mmlu)} | {fmt(gsm8k)} | {fmt(hellaswag)} | "
                        f"{fmt(arc_easy)} | {fmt(arc_challenge)} | {fmt(truthfulqa)} |"
                    )
                else:
                    report_lines.append(f"| {name} | FAILED | - | - | - | - | - |")
        
        report_lines.extend(["", "## Detailed Results", ""])
        
        for name, result in self.results.items():
            report_lines.append(f"### {name}")
            report_lines.append(f"- **Model Type**: {result['model_type']}")
            report_lines.append(f"- **Args**: {result['model_args']}")
            report_lines.append(f"- **Success**: {result['success']}")
            report_lines.append(f"- **Time**: {result.get('elapsed_seconds', 0):.1f}s")
            
            if result['success'] and result['metrics']:
                report_lines.append("- **Metrics**:")
                for task, metrics in result['metrics'].items():
                    for metric, value in metrics.items():
                        report_lines.append(f"  - {task}/{metric}: {value:.4f}")
            elif not result['success']:
                report_lines.append(f"- **Error**: {result['stderr'][:500]}")
            report_lines.append("")
        
        return '\n'.join(report_lines)
    
    def save_all(self):
        """Save all results and report."""
        # Save full results
        with open(self.output_base / 'all_results.json', 'w') as f:
            json.dump(self.results, f, indent=2)
        
        # Save report
        report = self.generate_report()
        with open(self.output_base / 'REPORT.md', 'w') as f:
            f.write(report)
        
        print(f"\nResults saved to: {self.output_base}")
        print(f"  - all_results.json (full data)")
        print(f"  - REPORT.md (comparison report)")
        print(f"  - <model>/result.json (per-model)")

def get_model_configs() -> List[Dict]:
    """Get model configurations to evaluate."""
    configs = []
    
    # Always include dummy for baseline
    configs.append({
        'name': 'dummy-baseline',
        'model_type': 'dummy',
        'model_args': '{}',
        'apply_chat_template': False,
        'fewshot_as_multiturn': False,
        'limit': 10,
    })
    
    # Add HF models if token available
    if os.environ.get('HF_TOKEN'):
        configs.extend([
            {
                'name': 'gemma-3-4b-it',
                'model_type': 'hf',
                'model_args': 'pretrained=google/gemma-3-4b-it,dtype=bfloat16,device_map=auto',
                'batch_size': 'auto',
            },
            {
                'name': 'gemma-2-2b-it',
                'model_type': 'hf',
                'model_args': 'pretrained=google/gemma-2-2b-it,dtype=bfloat16,device_map=auto',
                'batch_size': 'auto',
            },
        ])
    else:
        print("⚠ HF_TOKEN not set - skipping gated Gemma 2 models")
        print("  Set HF_TOKEN to evaluate: google/gemma-2-2b-it, google/gemma-2-9b-it")
    
    # Add GLM via local-completions if API key available
    if os.environ.get('ZHIPUAI_API_KEY'):
        configs.append({
            'name': 'glm-4-9b-chat',
            'model_type': 'local-chat-completions',
            'model_args': 'model=glm-4-9b-chat,base_url=https://api.z.ai/v1/chat/completions,num_concurrent=16,max_retries=3,tokenized_requests=false',
            'apply_chat_template': True,
            'fewshot_as_multiturn': True,
        })
    else:
        print("⚠ ZHIPUAI_API_KEY not set - skipping GLM-4 evaluation")
        print("  Get API key from https://open.bigmodel.cn")
    
    # Add local vLLM if running
    # User can manually add: base_url=http://localhost:8000/v1/chat/completions
    
    return configs

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Run model evaluations')
    parser.add_argument('--limit', type=int, help='Limit samples per task (for testing)')
    parser.add_argument('--output', default='./eval_results', help='Output directory')
    parser.add_argument('--models', nargs='+', help='Specific models to run (by name)')
    parser.add_argument('--list', action='store_true', help='List available model configs')
    args = parser.parse_args()
    
    output_base = Path(args.output)
    evaluator = ModelEvaluator(output_base)
    
    configs = get_model_configs()
    
    if args.list:
        print("Available model configurations:")
        for c in configs:
            print(f"  - {c['name']}: {c['model_type']} ({c['model_args'][:80]}...)")
        return
    
    if args.models:
        configs = [c for c in configs if c['name'] in args.models]
        if not configs:
            print(f"No matching models for: {args.models}")
            return
    
    print(f"Running evaluations for {len(configs)} model(s)")
    print(f"Output directory: {output_base}")
    
    for config in configs:
        limit = args.limit if args.limit else config.get('limit')
        evaluator.evaluate_model(
            name=config['name'],
            model_type=config['model_type'],
            model_args=config['model_args'],
            apply_chat_template=config.get('apply_chat_template', False),
            fewshot_as_multiturn=config.get('fewshot_as_multiturn', False),
            limit=limit,
            batch_size=config.get('batch_size', 'auto'),
        )
    
    evaluator.save_all()
    print("\n" + evaluator.generate_report())

if __name__ == '__main__':
    main()
