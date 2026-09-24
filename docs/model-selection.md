# Model selection record

Date: 2026-09-24

## Candidates

| Candidate | Licence | Relevant characteristics | Decision risk |
| --- | --- | --- | --- |
| [Qwen2.5-7B-Instruct](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct) | Apache-2.0 | 7B-class instruction model; model configuration declares a 32,768-token native context. Strong candidate for structured JSON and practical single-GPU quantised serving. | Must be evaluated on the fixed held-out ScribeBench set; general benchmarks do not establish clinical suitability. |
| [Mistral-7B-Instruct-v0.3](https://huggingface.co/mistralai/Mistral-7B-Instruct-v0.3) | Apache-2.0 | 7B-class instruction model with function-calling support and broad serving compatibility. | Shorter context margin for unusually long transcripts and the same domain-evaluation requirement. |

## Provisional selection

`Qwen/Qwen2.5-7B-Instruct` is the provisional self-hosted baseline because the licence is permissive, its declared context window leaves more room for long transcripts plus the output schema, and vLLM can expose it through an OpenAI-compatible endpoint. This is a deployment choice, not evidence of clinical quality.

The repository defaults to `rule-based-baseline-v1` so every test is reproducible without model downloads or GPU spend. Switching `SCRIBE_MODEL_PROVIDER=openai-compatible` activates the selected model adapter.

## Promotion gate

Qwen is promoted only if it beats the deterministic baseline on unsupported claims and omission handling without regressing refusal behaviour or structured-output validity. Mistral remains the fallback comparison. Record exact model revisions, quantisation, prompt, seed, hardware, concurrency, and raw evaluator artefacts.

