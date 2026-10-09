# Demo script (target 2:45–2:55, English captions throughout)

Setup: live mode (`APP_MODE=live`), "Start a private demo" (a fresh private session; or the jury account
`TestUser` / `TestUser11`), persona *Biman* (synthetic composite), ladder "2 readings a day", replay clock at day 7, 19:30. Reset the persona first (Profile →
reset) so every take starts from the same state. Record at 1440×900; label any time compression on screen.

| Time | Screen | Action | Caption / voice-over (English) |
|---|---|---|---|
| 0:00–0:15 | Login → Twin | Sign in; the clownfish passes once in the footer band | "NemoTwins: a glucose digital twin whose assistant runs on NVIDIA Nemotron through Nebius Token Factory. Research prototype — synthetic patient, not a medical device." |
| 0:15–0:35 | Twin | Point at the four tiles | "Measured: the last finger-prick, 12.5 h ago. Estimated: the twin's current value with its calibrated 90 % range. Forecast: the chance of going above 180 in 2 h, retrospectively evaluated. Everything is labelled by what it is." |
| 0:35–1:05 | Talk, Español | Tap "¿Qué pasa con mi glucosa si ceno arroz con lentejas?" | "No amount given — so the assistant asks one question before simulating, instead of guessing." Show the clarification card. |
| 1:05–1:25 | Talk | Tap "1 cuenco (katori)" | "Nemotron 3 Super calls the twin's forecast tool and explains the engine's numbers. Every number is checked against tool output; NeMo Guardrails checks input and output; stale data is disclosed." Open "¿Por qué esta respuesta?" briefly: tools, model id, checks. |
| 1:25–1:45 | Talk | Tap "¿Y si camino 15 minutos después de cenar?" | "A what-if is an exploratory simulation, paired on the same particles — never a proven effect, and if the difference is within simulation variability the twin says it can't rank them." |
| 1:45–2:05 | Language → Français / Deutsch | Ask the same meal question with "1" | "Switching language changes the words, not the numbers: same food ids, same engine result." Show identical peak and probability. |
| 2:05–2:25 | Twin → "Revelar la siguiente medición registrada" | Reveal and assimilate | "A recorded reading arrives. The twin updates — the band can narrow or, after a surprise, widen. We show what actually happened." |
| 2:25–2:40 | Trust / evidence receipt | Open the receipt | "Evidence: 45 CGMacros participants, 13,251 forecast windows, retrospective — not clinical validation. Negative results stay visible." Then the multilingual Nemotron suite result (EVALUATION.md). |
| 2:40–2:52 | Admin → Integrations | Show models, guardrails, usage, Cloud status | "Token Factory for every model call, NeMo Guardrails, live at nemotwins.koushikdeb.com; Nebius AI Cloud deployment scripts are included as an option." |

## Fallback plan

* **Token Factory slow or down**: replies switch to approved templates, visibly labelled "template"; the
  numbers still come from the engine. Record that take as-is or retake.
* **Japanese / French take fails**: use German; any of the six works.
* **Guardrail false positive**: rephrase the question; mention that deterministic checks remain authoritative.
* Keep a pre-recorded backup of the Spanish clarification take.
