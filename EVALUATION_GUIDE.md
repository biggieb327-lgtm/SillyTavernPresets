# Model Evaluation Guide: GLM & Gemma with lm-evaluation-harness

## Overview
This guide documents how to evaluate GLM (ZhipuAI) and Gemma (Google) models using the lm-evaluation-harness, integrated with the UnifiedWritersRoom_V32 preset repository.

## Current Status
✅ **Repository updated**: UnifiedWritersRoom_V32.json cleaned and pushed to GitHub
✅ **Harness installed**: lm-eval v0.4.7+ with API support
✅ **Test verified**: Dummy model runs successfully on all core benchmarks

## Benchmark Tasks Configured
| Task | Description | Metric |
|------|-------------|--------|
| `mmlu` | Massive Multitask Language Understanding | Accuracy |
| `gsm8k` | Grade School Math 8K | Exact Match |
| `hellaswag` | Commonsense Reasoning | Accuracy (norm) |
| `arc_easy` | AI2 Reasoning Challenge (Easy) | Accuracy |
| `arc_challenge` | AI2 Reasoning Challenge (Hard) | Accuracy |
| `truthfulqa` | Truthfulness Benchmark | MC1/MC2 Accuracy |

---

## Model Access Strategies

### Option 1: API-Based Evaluation (Recommended for GLM)
GLM-4 models are available via ZhipuAI's API. Use `local-chat-completions` model type with an OpenAI-compatible endpoint.

```bash
# Set up ZhipuAI API (get key from https://open.bigmodel.cn)
export ZHIPUAI_API_KEY="your-key-here"

# Run evaluation via local proxy or direct API
lm-eval run \
  --model local-chat-completions \
  --model_args model=glm-4,base_url=https://api.z.ai/v1/chat/completions,num_concurrent=16,max_retries=3,tokenized_requests=false \
  --tasks mmlu,gsm8k,hellaswag,arc_easy,arc_challenge,truthfulqa \
  --apply_chat_template \
  --fewshot_as_multiturn \
  --output_path ./eval_results/glm-4
```

### Option 2: Local HF Models (Gemma 2/3)
For Gemma models, use the `hf` model type. Note: Gemma 2 models are gated and require HF authentication.

```bash
# Login to HuggingFace
huggingface-cli login
# or export HF_TOKEN="your-token"

# Gemma 2 2B (smallest, most accessible)
lm-eval run \
  --model hf \
  --model_args pretrained=google/gemma-2-2b-it,dtype=bfloat16,device_map=auto \
  --tasks mmlu,gsm8k,hellaswag,arc_easy,arc_challenge,truthfulqa \
  --batch_size auto \
  --output_path ./eval_results/gemma-2-2b

# Gemma 3 4B (latest, public)
lm-eval run \
  --model hf \
  --model_args pretrained=google/gemma-3-4b-it,dtype=bfloat16,device_map=auto \
  --tasks mmlu,gsm8k,hellaswag,arc_easy,arc_challenge,truthfulqa \
  --batch_size auto \
  --output_path ./eval_results/gemma-3-4b
```

### Option 3: vLLM Server + local-completions (Best for Production)
Deploy models via vLLM for high-throughput evaluation.

```bash
# Start vLLM server (requires GPU for practical use)
vllm serve google/gemma-2-2b-it \
  --dtype bfloat16 \
  --max-model-len 8192 \
  --gpu-memory-utilization 0.8 \
  --port 8000

# In another terminal, run evaluation
lm-eval run \
  --model local-chat-completions \
  --model_args model=gemma-2-2b-it,base_url=http://localhost:8000/v1/chat/completions,num_concurrent=32,max_retries=3,tokenized_requests=false \
  --tasks mmlu,gsm8k,hellaswag,arc_easy,arc_challenge,truthfulqa \
  --apply_chat_template \
  --fewshot_as_multiturn \
  --output_path ./eval_results/gemma-2-2b-vllm
```

### Option 4: Quantized GGUF via llama.cpp (CPU-Friendly)
For CPU-only environments with memory constraints.

```bash
# Download quantized GGUF
wget https://huggingface.co/bartowski/gemma-2-2b-it-GGUF/resolve/main/gemma-2-2b-it-Q4_K_M.gguf

# Serve with llama.cpp
llama-server -m gemma-2-2b-it-Q4_K_M.gguf -c 8192 --port 8080

# Evaluate
lm-eval run \
  --model local-completions \
  --model_args model=gemma-2-2b-it,base_url=http://localhost:8080/completion,num_concurrent=8 \
  --tasks mmlu,gsm8k,hellaswag,arc_easy,arc_challenge,truthfulqa \
  --output_path ./eval_results/gemma-2-2b-gguf
```

---

## Quick Start Scripts

### Run All Available Models (Automated)
```bash
cd /root/SillyTavernPresets
python3 run_eval_full.py
```

### Manual Single Model Run
```bash
cd /root/SillyTavernPresets

# Quick test (10 samples per task)
lm-eval run --model dummy --tasks mmlu,gsm8k,hellaswag,arc_easy,arc_challenge,truthfulqa --limit 10

# Full evaluation (when model access is configured)
lm-eval run --model hf --model_args pretrained=google/gemma-3-4b-it,dtype=bfloat16 --tasks mmlu,gsm8k,hellaswag,arc_easy,arc_challenge,truthfulqa --batch_size auto --output_path ./eval_results/gemma-3-4b
```

---

## Results Interpretation

### Expected Baseline Ranges (Dummy Model)
| Task | Random Baseline | Dummy (10 samples) |
|------|-----------------|-------------------|
| MMLU | ~25% | ~26% |
| GSM8K | ~0% | ~0% |
| HellaSwag | ~25% | ~10-20% |
| ARC-Easy | ~25% | ~10% |
| ARC-Challenge | ~25% | ~20% |
| TruthfulQA MC1 | ~25% | ~30% |

### Real Model Targets (Approximate)
| Model | MMLU | GSM8K | HellaSwag | ARC-C | TruthfulQA |
|-------|------|-------|-----------|-------|------------|
| Gemma 2 2B | ~55% | ~35% | ~55% | ~50% | ~45% |
| Gemma 2 9B | ~70% | ~55% | ~70% | ~65% | ~55% |
| Gemma 3 4B | ~65% | ~45% | ~65% | ~60% | ~50% |
| GLM-4-9B | ~75% | ~65% | ~75% | ~70% | ~60% |

---

## Troubleshooting

### Memory Issues (2GB Container Limit)
- Use quantized models (4-bit GGUF)
- Use vLLM with `gpu_memory_utilization=0.6` if GPU available
- Reduce `--batch_size` to 1
- Use `--limit` for testing

### Gated Model Access
```bash
# Gemma 2 requires accepting terms at https://huggingface.co/google/gemma-2-2b-it
# Then: huggingface-cli login
# Or: export HF_TOKEN="hf_xxx"
```

### Authentication Errors
```bash
# For ZhipuAI/GLM
export ZHIPUAI_API_KEY="your-key"

# For HuggingFace
export HF_TOKEN="your-token"

# For OpenAI-compatible APIs
export OPENAI_API_KEY="your-key"
export OPENAI_BASE_URL="https://api.example.com/v1"
```

---

## Integration with UnifiedWritersRoom_V32

The preset includes sophisticated prompt engineering (ANVIL, NPC-PSYCH, SPUR, Prose Quality modules). To evaluate model quality on creative writing tasks:

1. **Custom Task Creation**: Add creative writing benchmarks to lm-eval
2. **Humanizer Skill**: Use the `humanizer` skill to strip AI-isms from outputs
3. **Comparative Analysis**: Run same prompts through multiple models

### Example Custom Task
```yaml
# custom_tasks/creative_writing.yaml
task: creative_writing
dataset_path: local
dataset_name: unified_writers_room
doc_to_text: "{{prompt}}"
doc_to_target: "{{reference}}"
metric_list:
  - metric: bleu
  - metric: rouge
  - metric: perplexity
```

---

## Files in Repository
```
/root/SillyTavernPresets/
├── UnifiedWritersRoom_V32.json          # Cleaned preset (pushed to GitHub)
├── DISCUSSIONS.md                        # Conversation log
├── eval_config.yaml                      # Evaluation configuration
├── run_eval.py                          # Python runner script
├── run_eval_full.py                     # Full automated runner
├── EVALUATION_GUIDE.md                  # This file
└── eval_results/                        # Output directory
    ├── dummy/                           # Test results
    ├── glm-4/                           # GLM-4 results (when run)
    ├── gemma-2-2b/                      # Gemma 2 2B results
    ├── gemma-2-9b/                      # Gemma 2 9B results
    └── gemma-3-4b/                      # Gemma 3 4B results
```

---

## Next Steps
1. **Obtain API keys**: ZhipuAI for GLM, HF token for Gemma 2
2. **Run evaluations**: Execute the commands above for each model
3. **Compare results**: Analyze benchmark scores across models
4. **Test with preset**: Use UnifiedWritersRoom_V32 prompts for qualitative evaluation
5. **Apply humanizer**: Post-process outputs with the humanizer skill

## Commands Run in This Session
```bash
# 1. Cleaned and pushed preset
git add UnifiedWritersRoom_V32.json && git commit -m "..." && git push

# 2. Installed evaluation harness
pip install lm-eval "lm-eval[api]" transformers accelerate torch bitsandbytes

# 3. Verified harness works
lm-eval run --model dummy --tasks hellaswag,arc_easy --limit 5

# 4. Ran full dummy test suite
python3 run_eval.py
```
