# Platform feedback (Nebius Token Factory, Nebius AI Cloud, NVIDIA Nemotron / NeMo Guardrails)

Observed while building NemoTwins on 2026-10-08. Concrete and dated; nothing here is hearsay.

## What worked well

* **Token Factory is a drop-in OpenAI-compatible endpoint.** Plain `httpx` calls worked first time; tool
  calling, `response_format: json_object` and `json_schema` all worked on Nemotron 3 Nano and Super.
* **`GET /v1/models`** made it possible to verify exact model ids instead of guessing from model cards.
* **`chat_template_kwargs.enable_thinking`** is accepted, and **`tool_choice: "required"`** works — both were
  decisive for latency and reliability.
* **Latency and reliability**: Nano ~0.7 s and Super ~1–2 s per call with thinking off. The three live
  evaluation runs (402 agent turns, ~1.6 M prompt tokens) logged no rate-limit, authentication, timeout or
  server error and no retry.
* **NeMo Guardrails 0.24** connects to Token Factory with `engine: openai` + `base_url`, no LangChain needed;
  self-check rails on Nano take ~0.3 s.
* **Nebius CLI**: `nebius ai endpoint create --dry-run`, clear `--help` (including MysteryBox `--env-secret`
  and managed HTTPS URLs), and actionable error hints. The Python SDK's `whoami()` is a perfect read-only
  credential check.

## Friction and shortcomings

1. **Reasoning tokens count against `max_tokens` with no warning.** Nemotron 3 Nano spent ~300 hidden tokens
   on a one-line answer and tool-using planner turns hit `finish_reason=length` even at 3,000 tokens. The
   switch exists but is only discoverable from the Hugging Face model card / vLLM docs. A Token Factory doc
   note and a per-request `reasoning: off` alias would save hours.
2. **`Nemotron-3_5-Lightning` in JSON mode** returned its reasoning ("Here's a thinking process…") as the
   content and was cut off — JSON mode and reasoning output should be mutually exclusive or documented.
3. **No NVIDIA vision, embedding or speech model** in this account's Token Factory catalog, so a fully
   NVIDIA multimodal path was impossible without leaving Token Factory. A Nemotron VL / NV-Embed / Parakeet
   or Riva-backed ASR offering would complete the story.
4. **Endpoint region is not reported** by the API (`/v1/models` has no region field).
5. **AI Serverless permissions**: `nebius ai endpoint create --dry-run` returned *PermissionDenied* for a
   freshly created federated user profile (request `90a2a1b3-e632-45eb-95e4-02977716865a`). The error does not
   say which role or activation is missing.
6. **CLI install** adds itself to `~/.bashrc`, so the current shell reports `nebius: command not found`
   until it is restarted — the installer message says so, but it is easy to miss.
7. **NeMo Guardrails self-check rails are not deterministic at temperature 0** on the same draft (one German
   draft was blocked once and passed three times later), so deterministic checks must stay authoritative.
8. **Model card vs catalog naming** (`NVIDIA-Nemotron-3-Nano-30B-A3B-BF16` on Hugging Face vs
   `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` on Token Factory) needs the catalog to be checked every time.
