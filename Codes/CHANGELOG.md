# Changelog

## 1.1.0 — 2026-10-10

- Sign-in page animation: a marble statue of a dressed man (MakeHuman CC0 body, posed on the twin's skeleton)
  revolves on the horizon; a clownfish of light passes through his heart one second after the page appears,
  and the stone dissolves into a glass copy of the same body with organs, blood, glucose and insulin flowing,
  before folding back. WebGL only, lazy-loaded; a still frame for reduced motion.
- Night screens (sign-in, Twin, Voice) have a black-to-blue gradient that drifts like a slow wave.
- What-if: 12 American food swaps (cola, fries, pancakes, sweet tea...), shown first alongside two Indian ones.
- "Start a private demo": one click creates a throw-away user per visitor, so reviewers no longer share
  replay clocks, readings and meals on the jury account; limited per client and per day, purged after 24 h.
- American meals: 38 USDA FNDDS foods (burgers, fries, pizza, pancakes, eggs, bacon, fried chicken, mac and
  cheese, steak, drinks, desserts) with names in all six languages, and five openly licensed American sample
  photos shown first on the Meal page. The photo prompt is no longer limited to Indian dish names, and
  ambiguous names ("pickle", "corn") follow the cuisine of the rest of the plate. Indian samples unchanged.

## 1.0.0 — 2026-10-09 — first release (Nebius × NVIDIA Global AI Hackathon)

- Glucose digital-twin engine: 7-state glucose–insulin model, CEM calibration, particle filter, learned
  residual, conformal bands, paired what-if simulations, experimental next-best-reading planner.
- Agent on NVIDIA Nemotron via Nebius Token Factory (Nemotron 3 Super planner, Nemotron 3 Nano router and
  guardrail rails): typed contract tools, one-question clarification, disclosures, evidence answers from the
  report receipt, numeric verifier, NVIDIA NeMo Guardrails input and output rails.
- Six languages (en-US, es-ES, fr-FR, de-DE, it-IT, ja-JP) in UI, assistant, safety rules and food names.
- Further reading for education questions from allowlisted health sites (Tavily search, display-only).
- Meal photos → dish candidates (Gemma 3 on Token Factory; nutrition from the food table).
- Evidence: retrospective evaluation reports, multilingual agent suite (48 cases × 6 languages), numerical
  regression harness, provider capability manifest.
- Self-hosted deployment (Caddy + uvicorn) and optional Nebius AI Cloud scripts.
