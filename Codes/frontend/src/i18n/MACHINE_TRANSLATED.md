# Machine-drafted locales: review required

`locales/en-US.json` is the source of truth and is bundled with the app. The other release
languages are separate, lazily loaded files drafted from it with the help of an AI model, following
`docs/TERMINOLOGY_GLOSSARY.md` in the repository root:

| File | Language |
|---|---|
| `locales/es-ES.json` | Spanish (Spain) |
| `locales/fr-FR.json` | French (France) |
| `locales/de-DE.json` | German (Germany) |
| `locales/it-IT.json` | Italian (Italy) |
| `locales/ja-JP.json` | Japanese |

These are the languages listed on the NVIDIA Nemotron 3 Nano model card. Listing a language there is
not evidence of domain-specific reliability, and no file has been reviewed by a fluent speaker or a
clinician yet. Before any real use, a native speaker with some clinical background must check each one.

## Rules

- Same key paths as `en-US.json`; `src/i18n/parity.test.ts` checks placeholders and empty strings.
  A key missing from a translation falls back to English at runtime.
- Keep every `{{placeholder}}` exactly as written.
- Never translate `NemoTwins`, `mg/dL`, `mmol/L`, CGM, HbA1c, model ids or dataset names.
- Emergency guidance stays location-neutral ("call your local emergency number"): no country number.
- Numbers, dates and times are formatted in code with `Intl` (decimal comma for es/fr/de/it,
  24-hour clock except en-US); translations never contain formatted numbers of their own.
