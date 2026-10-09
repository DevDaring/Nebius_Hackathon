# NemoTwins terminology glossary (en / es / fr / de / it / ja)

Status: **machine-drafted reference glossary, 2026-10-08 — pending review by fluent speakers and a
clinician.** Every UI string, assistant template and report in the six release languages uses these
terms. Do not substitute synonyms: the five evidence categories must stay distinguishable in every
language.

| Concept | English (en-US) | Español (es-ES) | Français (fr-FR) | Deutsch (de-DE) | Italiano (it-IT) | 日本語 (ja-JP) |
|---|---|---|---|---|---|---|
| Product name (never translated) | NemoTwins | NemoTwins | NemoTwins | NemoTwins | NemoTwins | NemoTwins |
| digital twin | digital twin | gemelo digital | jumeau numérique | digitaler Zwilling | gemello digitale | デジタルツイン |
| Twin (nav label) | Twin | Gemelo | Jumeau | Zwilling | Gemello | ツイン |
| blood glucose | glucose / blood glucose | glucosa / glucosa en sangre | glycémie | Blutzucker | glicemia | 血糖値 |
| **Measured** (observed reading, with time and source) | measured | medido | mesuré | gemessen | misurato | 実測 |
| **Estimated** (twin's current latent state) | estimated | estimado | estimé | geschätzt | stimato | 推定 |
| **Forecast** (future value at a horizon) | forecast | pronóstico | prévision | Prognose | previsione | 予測 |
| **Exploratory simulation** (hypothetical change) | exploratory simulation | simulación exploratoria | simulation exploratoire | explorative Simulation | simulazione esplorativa | 探索的シミュレーション |
| **Retrospective evaluation** (named dataset + protocol) | retrospective evaluation / retrospectively evaluated | evaluación retrospectiva / evaluado retrospectivamente | évaluation rétrospective / évalué rétrospectivement | retrospektive Evaluation / retrospektiv evaluiert | valutazione retrospettiva / valutato retrospettivamente | 後ろ向き評価 / 後ろ向きに評価済み |
| not validated | not validated | no validado | non validé | nicht validiert | non validato | 未検証 |
| prediction interval | prediction interval | intervalo de predicción | intervalle de prédiction | Vorhersageintervall | intervallo di previsione | 予測区間 |
| uncertainty | uncertainty | incertidumbre | incertitude | Unsicherheit | incertezza | 不確実性 |
| uncertainty band (chart) | uncertainty band | banda de incertidumbre | bande d'incertitude | Unsicherheitsband | banda di incertezza | 不確実性の幅 |
| finger-prick reading | finger-prick reading | medición capilar | glycémie capillaire | kapillare Messung | misurazione capillare | 指先採血の測定値 |
| reading (generic) | reading | medición | mesure | Messwert | misurazione | 測定値 |
| CGM | CGM (continuous glucose monitor) | MCG (monitor continuo de glucosa) | MCG (capteur de glucose en continu) | CGM (kontinuierliche Glukosemessung) | CGM (monitoraggio continuo del glucosio) | CGM（持続血糖測定） |
| carbohydrates (carbs) | carbohydrates (carbs) | hidratos de carbono | glucides | Kohlenhydrate | carboidrati | 炭水化物 |
| time in range | time in range | tiempo en rango | temps dans la cible | Zeit im Zielbereich | tempo nel range | 目標範囲内時間 |
| peak | peak | pico | pic | Spitzenwert | picco | ピーク |
| what-if | what-if | ¿Y si…? | Et si… ? | Was-wäre-wenn | E se…? | もしも |
| scenario | scenario | escenario | scénario | Szenario | scenario | シナリオ |
| stale data | stale data | datos desactualizados | données anciennes | veraltete Daten | dati non aggiornati | 古いデータ |
| replay clock | replay clock | reloj de reproducción | horloge de relecture | Wiedergabeuhr | orologio di riproduzione | 再生クロック |
| synthetic persona | synthetic persona | persona sintética | persona synthétique | synthetische Persona | persona sintetica | 合成ペルソナ |
| evidence receipt | evidence receipt | comprobante de evidencia | justificatif de preuves | Evidenznachweis | riepilogo delle evidenze | 根拠の記録 |
| research prototype | research prototype | prototipo de investigación | prototype de recherche | Forschungsprototyp | prototipo di ricerca | 研究用プロトタイプ |
| not a medical device | not a medical device | no es un producto sanitario | n'est pas un dispositif médical | kein Medizinprodukt | non è un dispositivo medico | 医療機器ではありません |

## Conventions

- **Units stay explicit:** `mg/dL` and `mmol/L` are never translated or dropped. The model never
  converts units; conversion happens in code.
- **Numbers:** decimal comma in es-ES, fr-FR, de-DE and it-IT (`7,2 mmol/L`), decimal point in en-US and ja-JP. Apply
  formatting only at display time (`Intl.NumberFormat`); stored values stay canonical.
- **Times:** 24-hour clock in es-ES, fr-FR, de-DE, it-IT and ja-JP; 12-hour clock in en-US. Always show the day when a
  time is not on the replay clock's current day.
- **Emergency guidance is location-neutral** ("call your local emergency number"); locale is not
  location, so no country-specific number is shown.
- Register: es-ES and de-DE use the polite form (usted / Sie); fr-FR uses vous; it-IT uses Lei; ja-JP uses です/ます.
