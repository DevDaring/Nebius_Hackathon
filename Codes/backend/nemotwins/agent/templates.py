"""Template replies built directly from tool outputs, in the six release languages.

Used (a) in offline demo mode and (b) as the fallback when an LLM draft fails the
numeric grounding verifier twice. Every number comes from a tool output, so these
always pass verification; every language uses exactly the same numbers as en-US.
Terms follow docs/TERMINOLOGY_GLOSSARY.md (es-ES usted, fr-FR vous, de-DE Sie, it-IT Lei,
ja-JP です/ます). Translations are machine-drafted and pending review by fluent speakers.
"""

from __future__ import annotations

from datetime import datetime

LANGS = ("en-US", "es-ES", "fr-FR", "de-DE", "it-IT", "ja-JP")
DEFAULT = "en-US"

T: dict[str, dict[str, str]] = {
    "state": {
        "en-US": "Right now your glucose is about {est}, most likely between {lo} and {hi}. In the next 2 hours the chance of going above 180 is {phigh_freq}.",
        "es-ES": "Ahora mismo su glucosa está en torno a {est}, lo más probable entre {lo} y {hi}. En las próximas 2 horas superaría 180 {phigh_freq}.",
        "fr-FR": "En ce moment, votre glycémie est d'environ {est}, très probablement entre {lo} et {hi}. Dans les 2 prochaines heures, elle dépasserait 180 {phigh_freq}.",
        "de-DE": "Ihr Blutzucker liegt gerade bei etwa {est}, sehr wahrscheinlich zwischen {lo} und {hi}. In den nächsten 2 Stunden läge er {phigh_freq} über 180.",
        "it-IT": "In questo momento la sua glicemia è circa {est}, molto probabilmente tra {lo} e {hi}. Nelle prossime 2 ore supererebbe 180 {phigh_freq}.",
        "ja-JP": "現在の血糖値はおよそ{est}で、{lo}から{hi}の間である可能性が高いです。今後2時間で180を超える確率は{phigh_freq}です。",
    },
    "forecast_meal": {
        "en-US": "If you eat {meal} now, about {carbs} grams of carbs, your glucose may peak near {peak} around {peak_time}. Chance of going above 180: {phigh_freq}.",
        "es-ES": "Si come ahora {meal}, unos {carbs} gramos de hidratos de carbono, su glucosa podría alcanzar un pico cercano a {peak} hacia las {peak_time}. Probabilidad de superar 180: {phigh_freq}.",
        "fr-FR": "Si vous mangez maintenant {meal}, soit environ {carbs} grammes de glucides, votre glycémie pourrait atteindre un pic proche de {peak} vers {peak_time}. Probabilité de dépasser 180 : {phigh_freq}.",
        "de-DE": "Wenn Sie jetzt {meal} essen, etwa {carbs} Gramm Kohlenhydrate, könnte Ihr Blutzucker gegen {peak_time} Uhr einen Spitzenwert von etwa {peak} erreichen. Wahrscheinlichkeit, über 180 zu steigen: {phigh_freq}.",
        "it-IT": "Se mangia ora {meal}, circa {carbs} grammi di carboidrati, la sua glicemia potrebbe raggiungere un picco vicino a {peak} verso le {peak_time}. Probabilità di superare 180: {phigh_freq}.",
        "ja-JP": "今{meal}を食べると（炭水化物 約{carbs}グラム）、{peak_time}ごろに血糖値が{peak}前後のピークに達する可能性があります。180を超える確率：{phigh_freq}。",
    },
    "whatif": {
        "en-US": "{label}: your peak changes by {dpeak}, and the chance of going above 180 moves from {p0} to {p1} percent.",
        "es-ES": "{label}: su pico cambia en {dpeak}, y la probabilidad de superar 180 pasa del {p0} al {p1} por ciento.",
        "fr-FR": "{label} : votre pic change de {dpeak}, et la probabilité de dépasser 180 passe de {p0} à {p1} pour cent.",
        "de-DE": "{label}: Ihr Spitzenwert ändert sich um {dpeak}, und die Wahrscheinlichkeit, über 180 zu steigen, geht von {p0} auf {p1} Prozent.",
        "it-IT": "{label}: il suo picco cambia di {dpeak} e la probabilità di superare 180 passa dal {p0} al {p1} per cento.",
        "ja-JP": "{label}：ピークは{dpeak}変化し、180を超える確率は{p0}パーセントから{p1}パーセントになります。",
    },
    "whatif_small": {
        "en-US": "{label}: the difference is too small to call. It stays within what I'm unsure about.",
        "es-ES": "{label}: la diferencia es demasiado pequeña para afirmarla. Queda dentro de mi margen de incertidumbre.",
        "fr-FR": "{label} : la différence est trop faible pour conclure. Elle reste dans ma marge d'incertitude.",
        "de-DE": "{label}: Der Unterschied ist zu klein für eine Aussage. Er liegt innerhalb meiner Unsicherheit.",
        "it-IT": "{label}: la differenza è troppo piccola per poterla affermare. Rientra nella mia incertezza.",
        "ja-JP": "{label}：差が小さすぎて判断できません。私の不確実性の範囲内です。",
    },
    "nbp": {
        "en-US": "Check at {time}. That reading will teach me the most: it cuts my uncertainty by about {gain} percent.",
        "es-ES": "Mídase a las {time}. Esa medición es la que más me enseñará: reduce mi incertidumbre en torno a un {gain} por ciento.",
        "fr-FR": "Faites une mesure à {time}. C'est elle qui m'apprendra le plus : elle réduit mon incertitude d'environ {gain} pour cent.",
        "de-DE": "Messen Sie um {time} Uhr. Dieser Messwert hilft mir am meisten: Er verringert meine Unsicherheit um etwa {gain} Prozent.",
        "it-IT": "Misuri alle {time}. Quella misurazione mi insegnerà di più: riduce la mia incertezza di circa il {gain} per cento.",
        "ja-JP": "{time}に測ってください。その測定値がいちばん参考になり、私の不確実性がおよそ{gain}パーセント減ります。",
    },
    "reading": {
        "en-US": "Thank you, I've added your reading of {value}. My band just narrowed by {pct} percent.",
        "es-ES": "Gracias, he añadido su medición de {value}. Mi banda de incertidumbre se ha estrechado un {pct} por ciento.",
        "fr-FR": "Merci, j'ai ajouté votre mesure de {value}. Ma bande d'incertitude vient de se réduire de {pct} pour cent.",
        "de-DE": "Danke, ich habe Ihren Messwert von {value} hinzugefügt. Mein Unsicherheitsband ist gerade um {pct} Prozent schmaler geworden.",
        "it-IT": "Grazie, ho aggiunto la sua misurazione di {value}. La mia banda di incertezza si è appena ristretta del {pct} per cento.",
        "ja-JP": "ありがとうございます。{value}の測定値を追加しました。不確実性の幅が{pct}パーセント狭くなりました。",
    },
    "forecast_meal_lowcarb": {
        "en-US": "{meal} has very little carbohydrate, so it should barely move your glucose. With it, the twin expects a peak near {peak} around {peak_time}. Chance of going above 180: {phigh_freq}.",
        "es-ES": "{meal} tiene muy pocos hidratos de carbono, así que apenas debería mover su glucosa. Con ello, el gemelo prevé un pico cercano a {peak} hacia las {peak_time}. Probabilidad de superar 180: {phigh_freq}.",
        "fr-FR": "{meal} contient très peu de glucides, donc cela devrait à peine modifier votre glycémie. Avec ce repas, le jumeau prévoit un pic proche de {peak} vers {peak_time}. Probabilité de dépasser 180 : {phigh_freq}.",
        "de-DE": "{meal} enthält sehr wenige Kohlenhydrate und dürfte Ihren Blutzucker kaum verändern. Damit erwartet der Zwilling gegen {peak_time} Uhr einen Spitzenwert von etwa {peak}. Wahrscheinlichkeit, über 180 zu steigen: {phigh_freq}.",
        "it-IT": "{meal} contiene pochissimi carboidrati, quindi dovrebbe muovere appena la sua glicemia. Con questo, il gemello prevede un picco vicino a {peak} verso le {peak_time}. Probabilità di superare 180: {phigh_freq}.",
        "ja-JP": "{meal}は炭水化物がとても少ないため、血糖値はほとんど変わらないはずです。これを食べた場合、ツインは{peak_time}ごろに{peak}前後のピークを予測しています。180を超える確率：{phigh_freq}。",
    },
    "whatif_peak_same": {
        "en-US": "{label}: your peak stays about the same, and the chance of going above 180 moves from {p0} to {p1} percent.",
        "es-ES": "{label}: su pico se mantiene más o menos igual, y la probabilidad de superar 180 pasa del {p0} al {p1} por ciento.",
        "fr-FR": "{label} : votre pic reste à peu près le même, et la probabilité de dépasser 180 passe de {p0} à {p1} pour cent.",
        "de-DE": "{label}: Ihr Spitzenwert bleibt etwa gleich, und die Wahrscheinlichkeit, über 180 zu steigen, geht von {p0} auf {p1} Prozent.",
        "it-IT": "{label}: il suo picco resta più o meno uguale e la probabilità di superare 180 passa dal {p0} al {p1} per cento.",
        "ja-JP": "{label}：ピークはほぼ変わらず、180を超える確率は{p0}パーセントから{p1}パーセントになります。",
    },
    "whatif_peak_only": {
        "en-US": "{label}: your peak changes by {dpeak}, but the chance of going above 180 stays about {p0} percent.",
        "es-ES": "{label}: su pico cambia en {dpeak}, pero la probabilidad de superar 180 se mantiene en torno al {p0} por ciento.",
        "fr-FR": "{label} : votre pic change de {dpeak}, mais la probabilité de dépasser 180 reste d'environ {p0} pour cent.",
        "de-DE": "{label}: Ihr Spitzenwert ändert sich um {dpeak}, aber die Wahrscheinlichkeit, über 180 zu steigen, bleibt bei etwa {p0} Prozent.",
        "it-IT": "{label}: il suo picco cambia di {dpeak}, ma la probabilità di superare 180 resta intorno al {p0} per cento.",
        "ja-JP": "{label}：ピークは{dpeak}変化しますが、180を超える確率はおよそ{p0}パーセントのままです。",
    },
    "nbp_flat": {
        "en-US": "Any time after {time} is fine. Right now I am fairly sure of your glucose, so one more reading would teach me only a little.",
        "es-ES": "Cualquier momento después de las {time} está bien. Ahora mismo tengo bastante certeza sobre su glucosa, así que otra medición me enseñaría poco.",
        "fr-FR": "N'importe quel moment après {time} convient. En ce moment, j'ai une bonne idée de votre glycémie, donc une mesure de plus m'apprendrait peu.",
        "de-DE": "Jeder Zeitpunkt nach {time} Uhr ist in Ordnung. Ich bin mir bei Ihrem Blutzucker gerade ziemlich sicher, daher würde mir ein weiterer Messwert nur wenig Neues zeigen.",
        "it-IT": "Va bene qualsiasi momento dopo le {time}. In questo momento ho una buona certezza sulla sua glicemia, quindi un'altra misurazione mi insegnerebbe poco.",
        "ja-JP": "{time}以降ならいつでも大丈夫です。今は血糖値についてかなり確信があるので、もう一度測定しても新しくわかることは少しだけです。",
    },
    "reading_confirms": {
        "en-US": "Thank you, I've added your reading of {value}. It matches what I expected, so my band stays about the same.",
        "es-ES": "Gracias, he añadido su medición de {value}. Coincide con lo que esperaba, así que mi banda de incertidumbre se mantiene más o menos igual.",
        "fr-FR": "Merci, j'ai ajouté votre mesure de {value}. Elle correspond à ce que j'attendais, donc ma bande d'incertitude reste à peu près la même.",
        "de-DE": "Danke, ich habe Ihren Messwert von {value} hinzugefügt. Er entspricht meiner Erwartung, daher bleibt mein Unsicherheitsband etwa gleich.",
        "it-IT": "Grazie, ho aggiunto la sua misurazione di {value}. Corrisponde a quanto mi aspettavo, quindi la mia banda di incertezza resta più o meno uguale.",
        "ja-JP": "ありがとうございます。{value}の測定値を追加しました。予想どおりの値だったので、不確実性の幅はほぼ変わりません。",
    },
    "explain_small": {
        "en-US": "No single factor stands out right now: each one changes your peak only a little. The largest is {driver}.",
        "es-ES": "Ahora mismo no destaca ningún factor: cada uno cambia su pico solo un poco. El mayor es {driver}.",
        "fr-FR": "Aucun facteur ne se détache pour l'instant : chacun ne modifie votre pic que légèrement. Le plus important est {driver}.",
        "de-DE": "Im Moment sticht kein einzelner Faktor hervor: Jeder verändert Ihren Spitzenwert nur wenig. Der größte ist {driver}.",
        "it-IT": "Al momento nessun fattore spicca: ognuno cambia il suo picco solo di poco. Il più grande è {driver}.",
        "ja-JP": "今は特に目立つ要因はありません。どの要因もピークを少し変えるだけです。最も大きいのは{driver}です。",
    },
    "low_risk": {
        "en-US": "My estimate for going below 70 in the next 2 hours is {plow_freq}, but this low-glucose estimate is not validated yet: my training data had too few lows. If you feel shaky, sweaty or confused, take a finger-prick reading.",
        "es-ES": "Según mi estimación, en las próximas 2 horas bajaría de 70 {plow_freq}, pero esta estimación de glucosa baja aún no está validada: mis datos de entrenamiento tenían muy pocas bajadas. Si nota temblores, sudor o confusión, hágase una medición capilar.",
        "fr-FR": "Selon mon estimation, dans les 2 prochaines heures, votre glycémie descendrait sous 70 {plow_freq}, mais cette estimation n'est pas encore validée : mes données d'entraînement contenaient trop peu d'hypoglycémies. Si vous avez des tremblements, des sueurs ou une confusion, faites une glycémie capillaire.",
        "de-DE": "Nach meiner Schätzung läge Ihr Blutzucker in den nächsten 2 Stunden {plow_freq} unter 70, aber diese Schätzung ist noch nicht validiert: Meine Trainingsdaten enthielten zu wenige Unterzuckerungen. Wenn Sie zittrig sind, schwitzen oder sich verwirrt fühlen, machen Sie eine kapillare Messung.",
        "it-IT": "Secondo la mia stima, nelle prossime 2 ore la glicemia scenderebbe sotto 70 {plow_freq}, ma questa stima non è ancora validata: i miei dati di addestramento contenevano troppo poche ipoglicemie. Se ha tremori, sudorazione o confusione, faccia una misurazione capillare.",
        "ja-JP": "今後2時間で70を下回る確率の私の推定は{plow_freq}ですが、この低血糖の推定はまだ検証されていません（未検証）。学習データに低血糖が少なすぎたためです。震え、汗、混乱を感じたら、指先採血で測定してください。",
    },
    "explain": {
        "en-US": "The biggest reason is {driver}: it changes your peak by about {contrib}.",
        "es-ES": "La razón principal es {driver}: cambia su pico en unos {contrib}.",
        "fr-FR": "La raison principale est {driver} : cela modifie votre pic d'environ {contrib}.",
        "de-DE": "Der wichtigste Grund ist {driver}: Das verändert Ihren Spitzenwert um etwa {contrib}.",
        "it-IT": "Il motivo principale è {driver}: cambia il suo picco di circa {contrib}.",
        "ja-JP": "最大の理由は{driver}です。ピークをおよそ{contrib}変化させます。",
    },
    "meal_logged": {
        "en-US": "I've noted {meal}, about {carbs} grams of carbs. Your peak may reach {peak} around {peak_time}.",
        "es-ES": "He anotado {meal}, unos {carbs} gramos de hidratos de carbono. Su pico podría llegar a {peak} hacia las {peak_time}.",
        "fr-FR": "J'ai noté {meal}, environ {carbs} grammes de glucides. Votre pic pourrait atteindre {peak} vers {peak_time}.",
        "de-DE": "Ich habe {meal} notiert, etwa {carbs} Gramm Kohlenhydrate. Ihr Spitzenwert könnte gegen {peak_time} Uhr {peak} erreichen.",
        "it-IT": "Ho annotato {meal}, circa {carbs} grammi di carboidrati. Il suo picco potrebbe arrivare a {peak} verso le {peak_time}.",
        "ja-JP": "{meal}（炭水化物 約{carbs}グラム）を記録しました。{peak_time}ごろにピークが{peak}に達する可能性があります。",
    },
    "abstain": {
        "en-US": "I am not sure enough right now. Please take a finger-prick reading so I can see clearly again.",
        "es-ES": "Ahora mismo no tengo suficiente certeza. Hágase una medición capilar para que pueda volver a ver con claridad.",
        "fr-FR": "Je n'ai pas assez de certitude pour le moment. Faites une glycémie capillaire pour que je puisse de nouveau y voir clair.",
        "de-DE": "Ich bin mir gerade nicht sicher genug. Bitte machen Sie eine kapillare Messung, damit ich wieder klar sehen kann.",
        "it-IT": "In questo momento non ho abbastanza certezza. Faccia una misurazione capillare così posso tornare a vedere con chiarezza.",
        "ja-JP": "今は十分な確信がありません。もう一度はっきり把握できるよう、指先採血で測定してください。",
    },
    "outlook": {
        "en-US": "This is a projection, not a promise. If habits stay the same, time in range stays near {tir0} percent; with smaller rice portions and short walks it could reach {tir1} percent.",
        "es-ES": "Esto es una proyección, no una promesa. Si sus hábitos no cambian, el tiempo en rango se mantiene cerca del {tir0} por ciento; con raciones de arroz más pequeñas y paseos cortos podría llegar al {tir1} por ciento.",
        "fr-FR": "Ceci est une projection, pas une promesse. Si vos habitudes restent les mêmes, le temps dans la cible reste proche de {tir0} pour cent ; avec des portions de riz plus petites et de courtes marches, il pourrait atteindre {tir1} pour cent.",
        "de-DE": "Das ist eine Hochrechnung, kein Versprechen. Wenn Ihre Gewohnheiten gleich bleiben, liegt die Zeit im Zielbereich bei etwa {tir0} Prozent; mit kleineren Reisportionen und kurzen Spaziergängen könnte sie {tir1} Prozent erreichen.",
        "it-IT": "Questa è una proiezione, non una promessa. Se le abitudini restano le stesse, il tempo nel range resta vicino al {tir0} per cento; con porzioni di riso più piccole e brevi camminate potrebbe arrivare al {tir1} per cento.",
        "ja-JP": "これは見通しであり、約束ではありません。習慣が今のままなら、目標範囲内時間はおよそ{tir0}パーセントのままです。ご飯の量を減らし、短い散歩をすれば{tir1}パーセントに達する可能性があります。",
    },
    "education": {
        "en-US": "Time in range means the share of the day your glucose stays between 70 and 180. Higher is better. HbA1c shows your average glucose over about 3 months.",
        "es-ES": "El tiempo en rango es la parte del día en que su glucosa se mantiene entre 70 y 180. Cuanto más alto, mejor. La HbA1c muestra su glucosa media de unos 3 meses.",
        "fr-FR": "Le temps dans la cible est la part de la journée pendant laquelle votre glycémie reste entre 70 et 180. Plus il est élevé, mieux c'est. L'HbA1c reflète votre glycémie moyenne sur environ 3 mois.",
        "de-DE": "Die Zeit im Zielbereich ist der Anteil des Tages, in dem Ihr Blutzucker zwischen 70 und 180 liegt. Je höher, desto besser. Der HbA1c-Wert zeigt Ihren durchschnittlichen Blutzucker der letzten etwa 3 Monate.",
        "it-IT": "Il tempo nel range è la parte della giornata in cui la sua glicemia resta tra 70 e 180. Più è alto, meglio è. L'HbA1c indica la sua glicemia media degli ultimi 3 mesi circa.",
        "ja-JP": "目標範囲内時間とは、一日のうち血糖値が70から180の間にある時間の割合です。高いほど良い状態です。HbA1cは、およそ3か月間の平均血糖値を示します。",
    },
    "whatif_unknown": {
        "en-US": "I could not tell which change you mean. You can ask, for example: what if I take a short walk after dinner, or what if I eat roti instead of rice?",
        "es-ES": "No he podido saber a qué cambio se refiere. Puede preguntar, por ejemplo: ¿y si doy un paseo corto después de cenar?, o ¿y si como roti en lugar de arroz?",
        "fr-FR": "Je n'ai pas compris de quel changement vous parlez. Vous pouvez demander, par exemple : et si je fais une courte marche après le dîner, ou et si je mange un roti au lieu du riz ?",
        "de-DE": "Ich konnte nicht erkennen, welche Änderung Sie meinen. Sie können zum Beispiel fragen: Was wäre, wenn ich nach dem Abendessen kurz spazieren gehe, oder wenn ich Roti statt Reis esse?",
        "it-IT": "Non ho capito a quale cambiamento si riferisce. Può chiedere, per esempio: e se faccio una breve camminata dopo cena, o e se mangio roti invece del riso?",
        "ja-JP": "どの変更のことか分かりませんでした。たとえば「夕食後に少し散歩したら？」や「ご飯の代わりにロティを食べたら？」のように聞いてください。",
    },
    "reading_offer": {
        "en-US": "Thank you for your reading of {value}. Confirm below if you want me to add it to your twin.",
        "es-ES": "Gracias por su medición de {value}. Confirme abajo si quiere que la añada a su gemelo digital.",
        "fr-FR": "Merci pour votre mesure de {value}. Confirmez ci-dessous si vous voulez que je l'ajoute à votre jumeau numérique.",
        "de-DE": "Danke für Ihren Messwert von {value}. Bestätigen Sie unten, wenn ich ihn zu Ihrem digitalen Zwilling hinzufügen soll.",
        "it-IT": "Grazie per la sua misurazione di {value}. Confermi qui sotto se vuole che la aggiunga al suo gemello digitale.",
        "ja-JP": "{value}の測定値をありがとうございます。デジタルツインに追加する場合は、下で確認してください。",
    },
    "reading_widened": {
        "en-US": "Thank you, I've added your reading of {value}. It surprised me, so my 2-hour band widened by {pct} percent.",
        "es-ES": "Gracias, he añadido su medición de {value}. Me ha sorprendido, así que mi banda de incertidumbre a 2 horas se ha ensanchado un {pct} por ciento.",
        "fr-FR": "Merci, j'ai ajouté votre mesure de {value}. Elle m'a surpris, donc ma bande d'incertitude à 2 heures s'est élargie de {pct} pour cent.",
        "de-DE": "Danke, ich habe Ihren Messwert von {value} hinzugefügt. Er hat mich überrascht, daher ist mein Unsicherheitsband für 2 Stunden um {pct} Prozent breiter geworden.",
        "it-IT": "Grazie, ho aggiunto la sua misurazione di {value}. Mi ha sorpreso, quindi la mia banda di incertezza a 2 ore si è allargata del {pct} per cento.",
        "ja-JP": "ありがとうございます。{value}の測定値を追加しました。予想と違っていたため、2時間先の不確実性の幅が{pct}パーセント広がりました。",
    },
    "meal_offer": {
        "en-US": "Confirm below if you want me to log this meal now.",
        "es-ES": "Confirme abajo si quiere que registre esta comida ahora.",
        "fr-FR": "Confirmez ci-dessous si vous voulez que j'enregistre ce repas maintenant.",
        "de-DE": "Bestätigen Sie unten, wenn ich diese Mahlzeit jetzt eintragen soll.",
        "it-IT": "Confermi qui sotto se vuole che registri ora questo pasto.",
        "ja-JP": "この食事を今記録する場合は、下で確認してください。",
    },
    "action_cancelled": {
        "en-US": "Okay, I have not added it.",
        "es-ES": "De acuerdo, no lo he añadido.",
        "fr-FR": "D'accord, je ne l'ai pas ajouté.",
        "de-DE": "In Ordnung, ich habe es nicht hinzugefügt.",
        "it-IT": "D'accordo, non l'ho aggiunto.",
        "ja-JP": "わかりました。追加していません。",
    },
    "action_stale": {
        "en-US": "That reading is now more than 30 minutes old on the replay clock, so I did not add it as a current reading. Please enter a fresh one.",
        "es-ES": "Esa medición tiene ya más de 30 minutos en el reloj de reproducción, así que no la he añadido como medición actual. Introduzca una nueva.",
        "fr-FR": "Cette mesure date maintenant de plus de 30 minutes sur l'horloge de relecture, je ne l'ai donc pas ajoutée comme mesure actuelle. Veuillez en saisir une nouvelle.",
        "de-DE": "Dieser Messwert ist auf der Wiedergabeuhr inzwischen älter als 30 Minuten, daher habe ich ihn nicht als aktuellen Messwert hinzugefügt. Bitte geben Sie einen neuen ein.",
        "it-IT": "Quella misurazione ha ormai più di 30 minuti sull'orologio di riproduzione, quindi non l'ho aggiunta come misurazione attuale. Ne inserisca una nuova.",
        "ja-JP": "その測定値は再生クロック上で30分以上前のものになったため、現在の測定値としては追加していません。新しい測定値を入力してください。",
    },
}

# What-if labels (the "{label}:" that starts a what-if reply).
WHATIF_LABEL: dict[str, dict[str, str]] = {
    "generic": {"en-US": "With this change", "es-ES": "Con este cambio", "fr-FR": "Avec ce changement",
                "de-DE": "Mit dieser Änderung", "it-IT": "Con questo cambiamento", "ja-JP": "この変更では"},
    "swap": {"en-US": "{new} instead of {old}", "es-ES": "{new} en lugar de {old}", "fr-FR": "{new} au lieu de {old}",
             "de-DE": "{new} statt {old}", "it-IT": "{new} invece di {old}", "ja-JP": "{old}の代わりに{new}"},
    "walk": {"en-US": "A {n}-minute walk after the meal", "es-ES": "Un paseo de {n} minutos después de comer",
             "fr-FR": "Une marche de {n} minutes après le repas", "de-DE": "Ein {n}-minütiger Spaziergang nach dem Essen",
             "it-IT": "Una camminata di {n} minuti dopo il pasto", "ja-JP": "食後に{n}分間散歩すると"},
    "half": {"en-US": "Half the {food}", "es-ES": "La mitad de {food}", "fr-FR": "La moitié de {food}",
             "de-DE": "Die halbe Portion {food}", "it-IT": "Mezza porzione di {food}", "ja-JP": "{food}を半分にすると"},
    "later": {"en-US": "Eating later", "es-ES": "Comer más tarde", "fr-FR": "Manger plus tard", "de-DE": "Später essen",
              "it-IT": "Mangiare più tardi", "ja-JP": "遅く食べると"},
    "earlier": {"en-US": "Eating earlier", "es-ES": "Comer antes", "fr-FR": "Manger plus tôt", "de-DE": "Früher essen",
                "it-IT": "Mangiare prima", "ja-JP": "早く食べると"},
}

# Physiology driver names from the twin (engine ``_driver_variants``) in plain words, per language.
# No medicine words here: a driver label can appear in an LLM draft, which the medication policy checks.
DRIVER_LABELS: dict[str, dict[str, str]] = {
    "meal_carbs": {"en-US": "the carbs in this meal", "es-ES": "los hidratos de carbono de esta comida",
                   "fr-FR": "les glucides de ce repas", "de-DE": "die Kohlenhydrate dieser Mahlzeit",
                   "it-IT": "i carboidrati di questo pasto", "ja-JP": "この食事の炭水化物"},
    "earlier_meals": {"en-US": "earlier food still digesting", "es-ES": "comida anterior que aún se está digiriendo",
                      "fr-FR": "un repas précédent encore en digestion",
                      "de-DE": "eine frühere Mahlzeit, die noch verdaut wird",
                      "it-IT": "cibo precedente ancora in digestione", "ja-JP": "まだ消化中の前の食事"},
    "insulin_sensitivity": {"en-US": "how your body handles sugar compared with most people",
                            "es-ES": "cómo maneja su cuerpo el azúcar en comparación con la mayoría de las personas",
                            "fr-FR": "la façon dont votre corps gère le sucre par rapport à la plupart des gens",
                            "de-DE": "wie Ihr Körper im Vergleich zu den meisten Menschen mit Zucker umgeht",
                            "it-IT": "come il suo corpo gestisce lo zucchero rispetto alla maggior parte delle persone",
                            "ja-JP": "ほかの多くの人と比べた、あなたの体の糖の処理のしかた"},
    "dawn_effect": {"en-US": "the time of day (your body clock)", "es-ES": "la hora del día (su reloj biológico)",
                    "fr-FR": "le moment de la journée (votre horloge biologique)",
                    "de-DE": "die Tageszeit (Ihre innere Uhr)", "it-IT": "l'ora del giorno (il suo orologio biologico)",
                    "ja-JP": "時間帯（体内時計）"},
    "recent_activity": {"en-US": "your recent activity", "es-ES": "su actividad reciente",
                        "fr-FR": "votre activité récente", "de-DE": "Ihre jüngste Aktivität",
                        "it-IT": "la sua attività recente", "ja-JP": "最近の活動"},
    "unexplained": {"en-US": "a recent trend the twin cannot explain",
                    "es-ES": "una tendencia reciente que el gemelo no puede explicar",
                    "fr-FR": "une tendance récente que le jumeau ne peut pas expliquer",
                    "de-DE": "ein aktueller Trend, den der Zwilling nicht erklären kann",
                    "it-IT": "una tendenza recente che il gemello non riesce a spiegare",
                    "ja-JP": "ツインが説明できない最近の傾向"},
}


DRIVER_NAME_BY_EN = {
    "Earlier food still digesting": "earlier_meals", "Your insulin sensitivity vs typical": "insulin_sensitivity",
    "Time of day (body clock)": "dawn_effect", "Recent activity": "recent_activity",
    "Recent unexplained trend": "unexplained",
}


def _pick(d: dict[str, str], lang: str) -> str:
    return d.get(lang, d[DEFAULT])


def driver_label(name: str | None, label_en: str, lang: str) -> str:
    """Localised driver label; unknown (learned) drivers keep their English label."""
    if not name:
        name = "meal_carbs" if label_en.startswith("This meal's carbs") else DRIVER_NAME_BY_EN.get(label_en)
    labels = DRIVER_LABELS.get(name or "")
    if labels:
        return _pick(labels, lang)
    return label_en[:1].lower() + label_en[1:] if lang == DEFAULT else label_en


def whatif_label(kind: str, lang: str, **kw: object) -> str:
    out = _pick(WHATIF_LABEL[kind], lang).format(**kw)
    return out[:1].upper() + out[1:] if out[:1].isascii() else out


# Frequencies ("N times out of 10"), worded so that "{phigh_freq}" works as an adverbial phrase.
FREQ = {
    "en-US": ("less than 1 time in 10", "about {n} times out of 10", "almost every time"),
    "es-ES": ("menos de 1 vez de cada 10", "unas {n} veces de cada 10", "casi siempre"),
    "fr-FR": ("moins d'1 fois sur 10", "environ {n} fois sur 10", "presque à chaque fois"),
    "de-DE": ("weniger als 1 von 10 Malen", "etwa {n} von 10 Malen", "fast jedes Mal"),
    "it-IT": ("meno di 1 volta su 10", "circa {n} volte su 10", "quasi ogni volta"),
    "ja-JP": ("10回中1回未満", "10回中およそ{n}回", "ほぼ毎回"),
}

# 12-hour clock for en-US, 24-hour clock for the other languages (glossary conventions).
AMPM = {"en-US": ("am", "pm")}


def freq(p: float, lang: str) -> str:
    lo, mid, hi = FREQ.get(lang, FREQ[DEFAULT])
    n = int(round(p * 10))
    if n <= 0:
        return lo
    if n >= 10:
        return hi
    return mid.format(n=n)


def clock(iso: str | None, lang: str) -> str:
    """Clock time of an ISO timestamp: '9:40 pm' (en-US, and unknown languages) or '21:40'."""
    if not iso:
        return ""
    dt = datetime.fromisoformat(iso)
    if lang in LANGS and lang not in AMPM:
        return f"{dt.hour}:{dt.minute:02d}"
    am, pm = AMPM[DEFAULT]
    h12 = (dt.hour % 12) or 12
    return f"{h12}:{dt.minute:02d} {am if dt.hour < 12 else pm}"


DECIMAL_COMMA = {"es-ES", "fr-FR", "de-DE", "it-IT"}


def number(v: float, lang: str, digits: int = 1) -> str:
    """A decimal number for display: decimal comma for es/fr/de/it ('7,2'), point otherwise.
    Whole numbers have no decimals. The verifier reads both forms."""
    r = round(float(v), digits)
    s = str(int(r)) if float(r).is_integer() else f"{r:.{digits}f}".rstrip("0").rstrip(".")
    return s.replace(".", ",") if lang in DECIMAL_COMMA else s


def render(key: str, lang: str, claims: list | None = None, **kw: object) -> str:
    """Fill a template. Values may be ``agent.slots.Slot`` objects (anything with ``rendered`` and
    ``claim()``): their rendered text is used and, when ``claims`` is given, their claim is recorded."""
    tpl = _pick(T[key], lang)
    vals: dict[str, object] = {}
    for k, v in kw.items():
        if hasattr(v, "rendered") and hasattr(v, "claim"):
            vals[k] = v.rendered
            if claims is not None and "{" + k + "}" in tpl:
                claims.append(v.claim())
        else:
            vals[k] = v
    out = tpl.format(**vals)
    # A dish name at the very start of a sentence ("boiled egg has ...") reads better capitalised.
    return out[:1].upper() + out[1:] if out[:1].isascii() else out


def signed(v: float) -> str:
    return f"{'+' if v >= 0 else '-'}{abs(round(v))}"
