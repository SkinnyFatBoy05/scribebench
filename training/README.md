# LoRA training scaffold

This directory is intentionally reproducible but not claimed as executed. Training should begin only after a recorded base-model evaluation identifies a specific weakness.

1. Freeze `api/data/synthetic_cases.json` and keep every `split=test` scenario family out of training and prompt iteration.
2. Create synthetic transcript/draft JSONL for `train` and `validation` only, retaining generator version and manual-review status.
3. Record the exact base model revision, package lock, seed, GPU, prompt template, hyperparameters, and output digest.
4. Run `uv run --with-requirements training/requirements.txt training/train_lora.py ...` on approved GPU infrastructure.
5. Re-run the unchanged held-out evaluator and retain regressions. Promote the adapter only if its acceptance gate passes.

The script refuses examples whose `split` is `test` and writes a checkpoint metadata file. It does not upload checkpoints.

