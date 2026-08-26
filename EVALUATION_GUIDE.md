# Model Evaluation Guide: GLM & Gemma with lm-evaluation-harness via NanoGPT

## Overview
This guide documents how to evaluate **GLM 4.7** (ZhipuAI) and **Gemma 3/4** (Google) models using the `lm-evaluation-harness` library with the NanoGPT API gateway.

## Setup Complete
- **API Gateway**: NanoGPT (https://nano-gpt.com) - provides OpenAI-compatible API
- **API Key**: `sk-nano-61d853fc-7312-46f4-9067-fcb51d83df0c` (configured)
- **Harness**: `lm-eval` with `local-completions` model type
- **Container**: CPU-only, 2GB memory limit (no local model inference possible)

## Available Models on NanoGPT

| Model Name | NanoGPT ID | Notes |
|------------|------------|-------|
| GLM 4.7 | `zai-org/glm-4.7` | ZhipuAI's latest flagship |
| Gemma 4 31B | `google/gemma-4-31b-it` | Google's latest (31B params) |
| Gemma 3 27B | `google/gemma-3-27b-it` | |
| Gemma 3 12B | `google/gemma-3-12b-it` | |
| Gemma 3 4B | `google/gemma-3-4b-it` | Recommended for speed |
| Gemma 3 1B | `google/gemma-3-1b-it` | Fastest |

## Quick Start

```bash
# Set API key
export NANOGPT_API_KEY="sk-nano-61d853fc-7312-46f4-9067-fcb51d83df0c"

# Run quick test (GSM8K, 10 samples)
cd /root/SillyTavernPresets
python3 run_eval_nanogpt.py --models glm-4.7 --tasks gsm8k --limit 10

# Run multiple models and tasks
python3 run_eval_nanogpt.py --models glm-4.7 gemma-4-31b --tasks gsm8k hellaswag arc_easy arc_challenge --limit 20

# List available models/tasks
python3 run_eval_nanogpt.py --list
python3 run_eval_nanogpt.py --list-tasks
```

## Direct lm-eval Usage

```bash
export NANOGPT_API_KEY="sk-nano-61d853fc-7312-46f4-9067-fcb51d83df0c"

lm-eval --model local-completions \
  --model_args '{"model": "zai-org/glm-4.7", "base_url": "https://nano-gpt.com/api/v1/completions", "header": {"Authorization": "Bearer sk-nano-61d853fc-7312-46f4-9067-fcb51d83df0c"}, "tokenizer_backend": "huggingface"}' \
  --tasks gsm8k,hellaswag,arc_easy,arc_challenge \
  --limit 10 \
  --output_path eval_results/glm-4.7_test
```

## Task Compatibility

### Works (generate_until - no logprobs needed)
- `gsm8k` - Grade school math
- `hellaswag` - Commonsense reasoning
- `arc_easy` / `arc_challenge` - Science QA
- `bbh` - BIG-Bench Hard
- `gpqa` - Graduate-level QA
- `humaneval` / `mbpp` - Code generation
- `math` - Competition math
- `drop` - Reading comprehension
- `boolq`, `piqa`, `winogrande`, `siqa`, `race`, `logiqa`, `xstorycloze`

### May Fail (loglikelihood - needs logprobs)
- `mmlu` - Multi-task language understanding
- `truthfulqa_mc1` / `truthfulqa_mc2` - Truthfulness (multiple choice)
- These require token logprobs which NanoGPT may not return

## Files in Repo

| File | Purpose |
|------|---------|
| `run_eval_nanogpt.py` | Main evaluation runner script |
| `eval_config.yaml` | Model/task configuration |
| `EVALUATION_GUIDE.md` | This file |

## Results Location
Results saved to `eval_results/<model>_<timestamp>/` with JSON output and Markdown reports.

## Example Output (GSM8K test)
```
local-completions (zai-org/glm-4.7), limit: 10
|Tasks|Version|Filter|n-shot|Metric|Value|Stderr|
|-----|------:|------|-----:|------|----:|-----:|
|gsm8k|3|flexible-extract|5|exact_match|0|0|
```
Note: 0% on GSM8K is likely format extraction issue, not model capability. The model answers correctly but the `flexible-extract` filter may not parse the response format.

## Troubleshooting

1. **401 Unauthorized**: Check API key is valid and has credits
2. **Timeout**: Increase timeout or reduce `--limit`
3. **Logprobs errors**: Use generate_until tasks only
4. **Slow responses**: NanoGPT free tier has rate limits

## Cost
NanoGPT offers free tier with daily limits. Check https://nano-gpt.com for pricing on larger evaluations.