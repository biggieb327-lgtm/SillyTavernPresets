#!/usr/bin/env python3
"""
Run evaluations for GLM and Gemma models using lm-evaluation-harness.
This script documents the evaluation process and handles various model access patterns.
"""

import subprocess
import json
import os
import sys
from pathlib import Path

def run_evaluation(model_type, model_args, tasks, output_dir, limit=None, apply_chat_template=False, fewshot_as_multiturn=False):
    """Run lm-eval with the specified model and tasks."""
    
    # Build command
    cmd = [
        'lm-eval', 'run',
        '--model', model_type,
        '--model_args', model_args,
        '--tasks', ','.join(tasks),
        '--output_path', output_dir,
    ]
    
    if limit:
        cmd.extend(['--limit', str(limit)])
    if apply_chat_template:
        cmd.append('--apply_chat_template')
    if fewshot_as_multiturn:
        cmd.append('--fewshot_as_multiturn')
    
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    
    return {
        'command': ' '.join(cmd),
        'exit_code': result.returncode,
        'stdout': result.stdout,
        'stderr': result.stderr
    }

def main():
    # Configuration
    tasks = ['mmlu', 'gsm8k', 'hellaswag', 'arc_easy', 'arc_challenge', 'truthfulqa']
    output_base = Path('./eval_results')
    output_base.mkdir(exist_ok=True)
    
    # Test models - using dummy for verification first
    test_configs = [
        {
            'name': 'dummy',
            'model_type': 'dummy',
            'model_args': '{}',
            'apply_chat_template': False,
            'fewshot_as_multiturn': False,
        }
    ]
    
    print("=" * 60)
    print("LM Evaluation Harness - Test Run")
    print("=" * 60)
    print(f"Tasks: {tasks}")
    print(f"Output: {output_base}")
    print()
    
    results = {}
    for config in test_configs:
        print(f"\nTesting {config['name']}...")
        output_dir = output_base / config['name']
        output_dir.mkdir(exist_ok=True)
        
        result = run_evaluation(
            model_type=config['model_type'],
            model_args=config['model_args'],
            tasks=tasks,
            output_dir=str(output_dir),
            limit=10,  # Quick test
            apply_chat_template=config.get('apply_chat_template', False),
            fewshot_as_multiturn=config.get('fewshot_as_multiturn', False),
        )
        
        results[config['name']] = result
        
        if result['exit_code'] == 0:
            print(f"  ✓ Success")
            # Extract key metrics
            for line in result['stdout'].split('\n'):
                if '|' in line and ('acc' in line or 'acc_norm' in line or 'em' in line or 'f1' in line):
                    print(f"  {line.strip()}")
        else:
            print(f"  ✗ Failed: {result['stderr'][:200]}")
    
    # Save results
    with open(output_base / 'test_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    print("\n" + "=" * 60)
    print("Test complete. Results saved to:", output_base / 'test_results.json')
    print("=" * 60)
    
    return results

if __name__ == '__main__':
    main()
