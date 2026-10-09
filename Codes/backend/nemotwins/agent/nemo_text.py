"""Localised fixed texts for the NemoTwins agent behaviours (clarification, disclosures, rail refusals).

Six release languages (the NVIDIA Nemotron 3 Nano model card list). Terms follow
docs/TERMINOLOGY_GLOSSARY.md. Machine-drafted 2026-10-08; pending review by fluent speakers.
Every ``{placeholder}`` is filled by code from tool outputs, never by the language model.
"""

from __future__ import annotations

LANGS = ("en-US", "es-ES", "fr-FR", "de-DE", "it-IT", "ja-JP")

T: dict[str, dict[str, str]] = {
    # ---- clarification
    "clarify_portion": {
        "en-US": "How much {food} will you have? The amount changes the simulation a lot.",
        "es-ES": "¿Cuánto {food} va a tomar? La cantidad cambia mucho la simulación.",
        "fr-FR": "Quelle quantité de {food} allez-vous prendre ? La quantité change beaucoup la simulation.",
        "de-DE": "Wie viel {food} essen Sie? Die Menge verändert die Simulation stark.",
        "it-IT": "Quanto {food} mangerà? La quantità cambia molto la simulazione.",
        "ja-JP": "{food}はどのくらい食べますか？量によってシミュレーションが大きく変わります。",
    },
    "clarify_unit": {
        "en-US": "Was {value} measured in mg/dL or mmol/L?",
        "es-ES": "¿{value} se midió en mg/dL o en mmol/L?",
        "fr-FR": "La valeur {value} était-elle en mg/dL ou en mmol/L ?",
        "de-DE": "Wurde {value} in mg/dL oder in mmol/L gemessen?",
        "it-IT": "Il valore {value} era in mg/dL o in mmol/L?",
        "ja-JP": "{value} の単位は mg/dL ですか、それとも mmol/L ですか？",
    },
    "skip_portion": {
        "en-US": "Not sure — use a wider range",
        "es-ES": "No lo sé: usar un rango más amplio",
        "fr-FR": "Je ne sais pas : utiliser une plage plus large",
        "de-DE": "Weiß nicht – breiteren Bereich verwenden",
        "it-IT": "Non so: usare un intervallo più ampio",
        "ja-JP": "わからない（幅を広げて計算）",
    },
    "skip_unit": {
        "en-US": "I don't know the unit",
        "es-ES": "No sé la unidad",
        "fr-FR": "Je ne connais pas l'unité",
        "de-DE": "Ich kenne die Einheit nicht",
        "it-IT": "Non conosco l'unità",
        "ja-JP": "単位がわかりません",
    },
    "unit_unknown": {
        "en-US": "Without the unit I cannot add this reading reliably, so I have not used it. Please check the meter's display for mg/dL or mmol/L.",
        "es-ES": "Sin la unidad no puedo añadir esta medición de forma fiable, así que no la he usado. Compruebe en la pantalla del medidor si indica mg/dL o mmol/L.",
        "fr-FR": "Sans l'unité, je ne peux pas ajouter cette mesure de façon fiable ; je ne l'ai donc pas utilisée. Vérifiez sur l'écran du lecteur s'il indique mg/dL ou mmol/L.",
        "de-DE": "Ohne Einheit kann ich diesen Messwert nicht zuverlässig übernehmen und habe ihn daher nicht verwendet. Bitte prüfen Sie, ob Ihr Messgerät mg/dL oder mmol/L anzeigt.",
        "it-IT": "Senza l'unità non posso aggiungere questa misurazione in modo affidabile, quindi non l'ho usata. Controlli sul display del misuratore se indica mg/dL o mmol/L.",
        "ja-JP": "単位がわからないため、この測定値は正確に追加できず、使用していません。測定器の表示が mg/dL か mmol/L かをご確認ください。",
    },
    "portion_option": {
        "en-US": "{qty} {unit} (~{grams} g)", "es-ES": "{qty} {unit} (~{grams} g)", "fr-FR": "{qty} {unit} (~{grams} g)",
        "de-DE": "{qty} {unit} (~{grams} g)", "it-IT": "{qty} {unit} (~{grams} g)", "ja-JP": "{unit}{qty}（約{grams} g）",
    },
    # ---- disclosures
    "disclose_stale": {
        "en-US": "The last reading was {hours} hours ago (replay clock), so the current estimate is less certain.",
        "es-ES": "La última medición fue hace {hours} horas (reloj de reproducción), así que la estimación actual es menos segura.",
        "fr-FR": "La dernière mesure date de {hours} heures (horloge de relecture) : l'estimation actuelle est donc moins sûre.",
        "de-DE": "Der letzte Messwert ist {hours} Stunden alt (Wiedergabeuhr), daher ist die aktuelle Schätzung unsicherer.",
        "it-IT": "L'ultima misurazione risale a {hours} ore fa (orologio di riproduzione), quindi la stima attuale è meno certa.",
        "ja-JP": "最後の測定値は{hours}時間前（再生クロック）のため、現在の推定の不確実性が大きくなっています。",
    },
    "disclose_no_reading": {
        "en-US": "There is no measured reading yet on the replay clock, so the current value is a model estimate only.",
        "es-ES": "Todavía no hay ninguna medición en el reloj de reproducción, así que el valor actual es solo una estimación del modelo.",
        "fr-FR": "Il n'y a encore aucune mesure sur l'horloge de relecture : la valeur actuelle n'est qu'une estimation du modèle.",
        "de-DE": "Auf der Wiedergabeuhr gibt es noch keinen Messwert; der aktuelle Wert ist nur eine Modellschätzung.",
        "it-IT": "Non c'è ancora nessuna misurazione sull'orologio di riproduzione, quindi il valore attuale è solo una stima del modello.",
        "ja-JP": "再生クロック上にまだ実測値がないため、現在の値はモデルの推定にすぎません。",
    },
    "disclose_exploratory": {
        "en-US": "Exploratory simulation: a model estimate of a hypothetical change, not a proven effect.",
        "es-ES": "Simulación exploratoria: una estimación del modelo para un cambio hipotético, no un efecto demostrado.",
        "fr-FR": "Simulation exploratoire : une estimation du modèle pour un changement hypothétique, pas un effet prouvé.",
        "de-DE": "Explorative Simulation: eine Modellschätzung für eine hypothetische Änderung, kein nachgewiesener Effekt.",
        "it-IT": "Simulazione esplorativa: una stima del modello per un cambiamento ipotetico, non un effetto dimostrato.",
        "ja-JP": "探索的シミュレーション：仮定の変化に対するモデルの推定であり、証明された効果ではありません。",
    },
    "disclose_ranking_uncertain": {
        "en-US": "The difference between these scenarios is within the twin's simulation variability, so they cannot be ranked with confidence.",
        "es-ES": "La diferencia entre estos escenarios está dentro de la variabilidad de simulación del gemelo, así que no se pueden ordenar con seguridad.",
        "fr-FR": "La différence entre ces scénarios reste dans la variabilité de simulation du jumeau : on ne peut pas les classer avec certitude.",
        "de-DE": "Der Unterschied zwischen diesen Szenarien liegt innerhalb der Simulationsschwankung des Zwillings; eine sichere Rangfolge ist nicht möglich.",
        "it-IT": "La differenza tra questi scenari rientra nella variabilità di simulazione del gemello, quindi non si possono ordinare con sicurezza.",
        "ja-JP": "これらのシナリオの差はツインのシミュレーションのばらつきの範囲内のため、確信をもって順位づけできません。",
    },
    "disclose_wider_range": {
        "en-US": "The portion was not specified, so the twin used the usual portion with a wider uncertainty for the amount eaten.",
        "es-ES": "No se indicó la cantidad, así que el gemelo usó la ración habitual con una incertidumbre más amplia sobre lo que se come.",
        "fr-FR": "La quantité n'a pas été précisée : le jumeau a utilisé la portion habituelle avec une incertitude plus large sur la quantité consommée.",
        "de-DE": "Die Menge wurde nicht angegeben; der Zwilling hat die übliche Portion mit größerer Unsicherheit über die verzehrte Menge verwendet.",
        "it-IT": "La quantità non è stata indicata, quindi il gemello ha usato la porzione abituale con un'incertezza più ampia sulla quantità consumata.",
        "ja-JP": "量が指定されなかったため、ツインは通常の量を使い、食べる量の不確実性を広げて計算しました。",
    },
    "disclose_not_validated": {
        "en-US": "The chance of going below 70 is not validated (too few low events in the training data).",
        "es-ES": "La probabilidad de bajar de 70 no está validada (demasiados pocos episodios bajos en los datos de entrenamiento).",
        "fr-FR": "La probabilité de passer sous 70 n'est pas validée (trop peu d'épisodes bas dans les données d'entraînement).",
        "de-DE": "Die Wahrscheinlichkeit, unter 70 zu fallen, ist nicht validiert (zu wenige niedrige Werte in den Trainingsdaten).",
        "it-IT": "La probabilità di scendere sotto 70 non è validata (troppi pochi episodi bassi nei dati di addestramento).",
        "ja-JP": "70未満になる確率は未検証です（学習データに低血糖のイベントが少なすぎるため）。",
    },
    "disclose_fallback": {
        "en-US": "This answer uses a fixed template filled from the twin's tools (the language model was unavailable or its draft failed a check).",
        "es-ES": "Esta respuesta usa una plantilla fija rellenada con las herramientas del gemelo (el modelo de lenguaje no estaba disponible o su borrador no pasó una comprobación).",
        "fr-FR": "Cette réponse utilise un modèle de texte fixe rempli par les outils du jumeau (le modèle de langage était indisponible ou son brouillon a échoué à une vérification).",
        "de-DE": "Diese Antwort verwendet eine feste Vorlage mit Werten aus den Werkzeugen des Zwillings (das Sprachmodell war nicht verfügbar oder sein Entwurf hat eine Prüfung nicht bestanden).",
        "it-IT": "Questa risposta usa un modello di testo fisso compilato con gli strumenti del gemello (il modello linguistico non era disponibile o la sua bozza non ha superato un controllo).",
        "ja-JP": "この回答は、ツインのツールの値を埋め込んだ定型文です（言語モデルが利用できなかったか、下書きが検証を通過しませんでした）。",
    },
    # ---- rails / evidence
    "rail_refusal": {
        "en-US": "I can't help with that here. I can explain your twin's estimates, forecasts and what-if simulations for meals, walks and readings.",
        "es-ES": "No puedo ayudar con eso aquí. Puedo explicar las estimaciones, pronósticos y simulaciones de su gemelo para comidas, paseos y mediciones.",
        "fr-FR": "Je ne peux pas vous aider sur ce point ici. Je peux expliquer les estimations, prévisions et simulations de votre jumeau pour les repas, la marche et les mesures.",
        "de-DE": "Dabei kann ich hier nicht helfen. Ich kann die Schätzungen, Prognosen und Simulationen Ihres Zwillings zu Mahlzeiten, Spaziergängen und Messwerten erklären.",
        "it-IT": "Non posso aiutarla su questo qui. Posso spiegare le stime, le previsioni e le simulazioni del Suo gemello per pasti, camminate e misurazioni.",
        "ja-JP": "その内容にはここではお答えできません。食事・散歩・測定値について、ツインの推定、予測、シミュレーションを説明できます。",
    },
    "evidence_answer": {
        "en-US": "That question goes beyond what this twin's evidence covers. Its forecasts were retrospectively evaluated on the {dataset} dataset ({n_patients} participants, {horizon}-minute horizon); that is not clinical validation, and it says nothing about long-term outcomes.",
        "es-ES": "Esa pregunta va más allá de lo que cubre la evidencia de este gemelo. Sus pronósticos se evaluaron retrospectivamente con el conjunto de datos {dataset} ({n_patients} participantes, horizonte de {horizon} minutos); eso no es una validación clínica y no dice nada sobre resultados a largo plazo.",
        "fr-FR": "Cette question dépasse ce que couvrent les preuves de ce jumeau. Ses prévisions ont été évaluées rétrospectivement sur le jeu de données {dataset} ({n_patients} participants, horizon de {horizon} minutes) ; ce n'est pas une validation clinique et cela ne dit rien des résultats à long terme.",
        "de-DE": "Diese Frage geht über die Evidenz dieses Zwillings hinaus. Seine Prognosen wurden retrospektiv am Datensatz {dataset} evaluiert ({n_patients} Teilnehmende, Horizont {horizon} Minuten); das ist keine klinische Validierung und sagt nichts über Langzeitfolgen aus.",
        "it-IT": "Questa domanda va oltre ciò che coprono le evidenze di questo gemello. Le sue previsioni sono state valutate retrospettivamente sul dataset {dataset} ({n_patients} partecipanti, orizzonte di {horizon} minuti); non è una validazione clinica e non dice nulla sugli esiti a lungo termine.",
        "ja-JP": "そのご質問は、このツインの根拠の範囲を超えています。予測は {dataset} データセット（参加者{n_patients}人、{horizon}分先まで）で後ろ向きに評価されたもので、臨床的な検証ではなく、長期的な結果については何も示していません。",
    },
}


# Household units of the food table (codes from the `unit` column), as short localised nouns.
UNITS: dict[str, dict[str, str]] = {
    "katori": {"en-US": "katori bowl", "es-ES": "cuenco (katori)", "fr-FR": "bol (katori)", "de-DE": "Schälchen (Katori)",
               "it-IT": "ciotola (katori)", "ja-JP": "小鉢（カトリ）"},
    "bowl": {"en-US": "bowl", "es-ES": "cuenco", "fr-FR": "bol", "de-DE": "Schüssel", "it-IT": "ciotola", "ja-JP": "椀"},
    "plate": {"en-US": "plate", "es-ES": "plato", "fr-FR": "assiette", "de-DE": "Teller", "it-IT": "piatto", "ja-JP": "皿"},
    "piece": {"en-US": "piece", "es-ES": "pieza", "fr-FR": "pièce", "de-DE": "Stück", "it-IT": "pezzo", "ja-JP": "個"},
    "serving": {"en-US": "serving", "es-ES": "ración", "fr-FR": "portion", "de-DE": "Portion", "it-IT": "porzione",
                "ja-JP": "人前"},
    "glass": {"en-US": "glass", "es-ES": "vaso", "fr-FR": "verre", "de-DE": "Glas", "it-IT": "bicchiere", "ja-JP": "杯"},
    "cup": {"en-US": "cup", "es-ES": "taza", "fr-FR": "tasse", "de-DE": "Tasse", "it-IT": "tazza", "ja-JP": "杯"},
    "tbsp": {"en-US": "tbsp", "es-ES": "cda.", "fr-FR": "c. à s.", "de-DE": "EL", "it-IT": "cucchiaio", "ja-JP": "大さじ"},
}


def unit_name(code: str, lang: str) -> str:
    u = UNITS.get(code)
    return (u.get(lang) or u["en-US"]) if u else code


def t(key: str, lang: str, **kw: object) -> str:
    entry = T[key]
    text = entry.get(lang) or entry["en-US"]
    return text.format(**kw) if kw else text
