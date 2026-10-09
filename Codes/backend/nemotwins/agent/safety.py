"""Safety filter (spec section 7.4): deterministic rules first, LLM second.

* Dose / medication-change requests are blocked with a fixed message.
* Reported symptoms of severe low or very high glucose trigger a fixed emergency
  message, regardless of what the planner would say.
* Diagnosis requests are refused.
* Prompt-injection attempts (e.g. inside a meal description) are neutralised: the
  text is treated as data and the attempt is flagged.

Languages: en-US, es-ES, fr-FR, de-DE, it-IT, ja-JP. Every pattern list below holds the English
rules first, then one block per language. Patterns are matched on ``_norm(text)`` (NFKC, lower
case: full-width Japanese digits/letters become ASCII). Japanese patterns never use ``\\b``.
Emergency guidance is location-neutral ("call your local emergency number"): locale is not location.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache

from nemotwins.agent.verifier import normalise_digits

LANGS = ("en-US", "es-ES", "fr-FR", "de-DE", "it-IT", "ja-JP")
DEFAULT_LANG = "en-US"

# ----------------------------------------------------------------------------- dose requests
# A drug / medication word plus an amount or change word (either order). English also keeps the
# romanised Hindi / Bengali / Kannada forms of the previous release as extra coverage (harmless,
# they only add blocking).
_EN_DRUGS = (r"insulin|metformin|glimepiride|gliclazide|sitagliptin|empagliflozin|dapagliflozin|semaglutide|ozempic|"
             r"glipizide|pioglitazone|vildagliptin|teneligliptin|lantus|novorapid|humalog|tablet|tablets|pill|pills|"
             r"medicine|medication|drug|dose|dosage|units?")
DOSE_EN = [
    rf"\b({_EN_DRUGS})\b.*\b(how much|how many|increase|decrease|reduce|double|"
    r"skip|stop|change|take|adjust|more|less|extra|inject)\b",
    r"\b(how much|how many|increase|decrease|reduce|double|skip|stop|change|adjust|extra|inject|take|more|less|"
    r"add|halve)\b.*\b(insulin|metformin|glimepiride|medicine|medication|tablet|tablets|pill|pills|dose|units?)\b",
    # gerund / past forms in either order: "whether skipping my evening glimepiride is fine"
    r"\b(skipp\w*|miss(?:ing|ed)|omit\w*|stopp\w*|chang(?:ing|ed)|increas\w*|decreas\w*|reduc\w*|doubl\w*|"
    r"halv\w*|adjust\w*)\b.{0,40}\b(insulin|metformin|glimepiride|gliclazide|sitagliptin|medicine|medicines|"
    r"medication|medications|tablet|tablets|pill|pills|dose|doses|units?)\b",
    r"\b(insulin|metformin|glimepiride|gliclazide|sitagliptin|medicine|medication|tablet|tablets|pill|pills|dose)\b"
    r".{0,40}\b(skipp\w*|miss(?:ing|ed)|omit\w*|stopp\w*|chang(?:ing|ed)|increas\w*|decreas\w*|reduc\w*|"
    r"doubl\w*|halv\w*)\b",
    # romanised Hindi / Bengali / Kannada (kept from the previous release)
    r"\b(insulin|metformin|glimepiride|dawa|dawai|davai|davaai|dawaai|goli|dose|medicine|tablet|units?)\b.*\b("
    r"kitna|kitni|kitne|badha\w*|badhau\w*|badhaun|ghata\w*|kam kar\w*|band kar\w*|chhod\w*|chod\w*|double|"
    r"dugna|doguna|lagau\w*|lagaun|loon|lun|le lu|le loon|kha lu)\b",
    r"\b(kitna|kitni|kitne)\b.*\b(insulin|dawa|dawai|davai|goli|dose|units?)\b",
    r"\b(oshudh|osudh|oshud|oushodh|oshudher|bori)\b.*\b(bondho|bando|baad|komabo|"
    r"kombo|komiye|barabo|baraabo|bariye|koto|kotota|khabo na|nebo na)\b",
    r"\b(aushadha|ausadha|aushada|maatre|matre)\b.*\b(beda|bidabahuda|bidabahudha|bidli|bidi|"
    r"bidona|hechchu|hechu|kadime|eshtu|nillisi|nilsi)\b",
]
_ES_DRUGS = (r"insulina\w*|metformina|glimepirida|gliclazida|sitagliptina|empagliflozina|dapagliflozina|semaglutida|"
             r"ozempic|lantus|novorapid|humalog|pastillas?|comprimidos?|medicinas?|medicamentos?|f[aá]rmacos?|dosis|"
             r"unidad(?:es)?")
_ES_CHANGE = (r"cu[aá]nt[oa]s?|aument\w*|subir|subo|bajar|bajo|reduc\w*|reduzco|disminu\w*|doblar|doblo|duplic\w*|"
              r"salt(?:ar|o|arme|armela|armelo)|me (?:la |lo )?salto|omit\w*|dejar de|dejo de|deja de|parar|paro|"
              r"suspend\w*|cambi\w*|ajust\w*|tomar|tomo|me tomo|pinch(?:ar|arme|o)|inyect\w*|m[aá]s|menos|extra|"
              r"olvid\w*")
_FR_DRUGS = (r"insuline\w*|metformine|glim[eé]piride|gliclazide|sitagliptine|empagliflozine|dapagliflozine|"
             r"s[eé]maglutide|ozempic|lantus|novorapid|humalog|comprim[eé]s?|cachets?|pilules?|g[eé]lules?|"
             r"m[eé]dicaments?|traitement|doses?|posologie|unit[eé]s?")
_FR_CHANGE = (r"combien|augment\w*|diminu\w*|r[eé]dui\w*|baisse\w*|doubl\w*|saute\w*|sauter|oubli\w*|arr[eê]t\w*|"
              r"chang\w*|ajust\w*|prendre|prends|prenne\w*|pris|injecte\w*|m'injecter|plus d[e']|moins d[e']|"
              r"en plus|suppl[eé]mentaire\w*")
_DE_DRUGS = (r"insulin\w*|metformin|glimepirid|gliclazid|sitagliptin|empagliflozin|dapagliflozin|semaglutid|ozempic|"
             r"lantus|novorapid|humalog|tablette\w*|pille\w*|medikament\w*|arznei\w*|medizin|dosis|dosierung|"
             r"einheit\w*")
_DE_CHANGE = (r"wie ?viel\w*|erh[oö]h\w*|erhoeh\w*|reduzier\w*|verringer\w*|senk\w*|verdoppel\w*|halbier\w*|auslass\w*|"
              r"weglass\w*|weg ?lassen|[uü]berspring\w*|absetz\w*|abzusetzen|setze\w*|aufh[oö]r\w*|stopp\w*|"
              r"[aä]nder\w*|aender\w*|anpass\w*|nehmen|nehme|genommen|spritz\w*|injizier\w*|mehr|weniger|"
              r"zus[aä]tzlich\w*|vergess\w*")
_IT_DRUGS = (r"insulina\w*|metformina|glimepiride|gliclazide|sitagliptin\w*|empagliflozin\w*|dapagliflozin\w*|"
             r"semaglutide|ozempic|lantus|novorapid|humalog|pastigli\w*|compress[ae]|pillol[ae]|farmac[oi]|"
             r"medicin[ae]|medicinal[ei]|dose|dosi|dosaggio|unit[aà]")
_IT_CHANGE = (r"quant[aoei]|aument\w*|diminui\w*|ridur\w*|riduco|abbass\w*|raddoppi\w*|saltar\w*|salto|smett\w*|"
              r"sospend\w*|interromp\w*|cambi\w*|aggiust\w*|modific\w*|prendere|prendo|iniett\w*|"
              r"di pi[uù]|di meno|in pi[uù]|extra|dimentic\w*")
_JA_DRUGS = r"インスリン|インシュリン|メトホルミン|グリメピリド|ランタス|ノボラピッド|ヒューマログ|オゼンピック|薬|くすり|錠剤|服薬|投与量|用量|単位"
_JA_CHANGE = (r"何単位|どれくらい|どのくらい|どれぐらい|いくつ|何錠|何ミリ|増や|減ら|倍|飛ばし|抜い|抜く|抜け|やめ|止め|"
              r"中止|変え|調整|打つ|打っ|打て|注射|飲む|飲め|飲ん|飲まな|多め|少なめ|追加|忘れ")
DOSE_I18N = [
    rf"\b({_ES_DRUGS})\b.{{0,60}}\b({_ES_CHANGE})\b", rf"\b({_ES_CHANGE})\b.{{0,60}}\b({_ES_DRUGS})\b",
    rf"\b({_FR_DRUGS})\b.{{0,60}}\b({_FR_CHANGE})", rf"\b({_FR_CHANGE}).{{0,60}}\b({_FR_DRUGS})\b",
    rf"\b({_DE_DRUGS})\b.{{0,60}}\b({_DE_CHANGE})\b", rf"\b({_DE_CHANGE})\b.{{0,60}}\b({_DE_DRUGS})\b",
    rf"\b({_IT_DRUGS})\b.{{0,60}}\b({_IT_CHANGE})", rf"\b({_IT_CHANGE}).{{0,60}}\b({_IT_DRUGS})\b",
    rf"({_JA_DRUGS}).{{0,30}}({_JA_CHANGE})", rf"({_JA_CHANGE}).{{0,30}}({_JA_DRUGS})",
]
# Dose phrasings without a separate change verb: compounds and "dose of insulin" forms.
DOSE_DIRECT = [
    r"\b(?:my|the) (?:insulin|metformin) dose\b|\bdose of (?:insulin|metformin)\b",
    r"\bdosis (?:de |de la )?(?:insulina|metformina)\b|\bmi dosis\b",
    r"\bdose d'(?:insuline|metformine)\b|\bma dose\b",
    r"\binsulin-?dosis\b|\bmetformin-?dosis\b|\bmeine (?:insulin)?dosis\b|\bdosis (?:insulin|metformin)\b",
    r"\bdose (?:di |dell'|della )(?:insulina|metformina)\b|\bla mia dose\b",
    r"インスリンの(?:量|単位|用量)|インスリン.{0,6}(?:何単位|単位数)|(?:薬|メトホルミン)の(?:量|用量)",
]
DOSE_PATTERNS = DOSE_EN + DOSE_I18N + DOSE_DIRECT

# ----------------------------------------------------------------------------- emergencies
# Symptoms that are an emergency on their own (gap-tolerant: "dolor muy fuerte en el pecho").
EMERGENCY_PATTERNS = [
    r"\b(unconscious|fainted|faint|fainting|passed out|collapsed|seizure|fits|convulsion\w*|can'?t wake|"
    r"not waking|not responding|unresponsive|cannot breathe|can'?t breathe|very low sugar|"
    r"sugar (?:is )?(?:below|under) ?(?:50|54|40)|vomiting and drowsy|fruity breath)\b",
    r"\b(?:trouble|difficulty|struggling to) breath\w*|\bshort(?:ness)? of breath\b",
    r"\bchest\b.{0,30}\b(?:pain|ache|aching|pressure|tightness)\b", r"\b(?:pain|ache|pressure|tightness)\b.{0,30}\bchest\b",
    r"\bbehosh\b|\bseene me\w* .{0,12}dard\b",  # romanised Hindi (previous release)
    # es-ES
    r"\b(?:inconsciente|se (?:ha )?desmayad[oa]|se desmay[oó]|desmay(?:o|ado|ada|arse|ándose)|perdi[oó] el conocimiento|"
    r"p[eé]rdida de conocimiento|convulsi\w*|ataque epil[eé]ptico|no (?:se )?despierta|no responde|no puedo respirar|"
    r"no puede respirar|me ahogo|dificultad (?:para|al) respirar|me falta el aire|falta de aire|"
    r"(?:az[uú]car|glucosa) muy baj[oa]|aliento afrutado)\b",
    r"\bpecho\b.{0,30}\b(?:dolor|presi[oó]n|opresi[oó]n)\b", r"\b(?:dolor|presi[oó]n|opresi[oó]n)\b.{0,30}\bpecho\b",
    # fr-FR
    r"\b(?:inconscient\w*|[eé]vanoui\w*|perdu connaissance|perte de connaissance|convulsion\w*|crise d'[eé]pilepsie|"
    r"crise convulsive|ne se r[eé]veille pas|ne r[eé]pond (?:pas|plus)|n'arrive (?:pas|plus) [aà] respirer|"
    r"ne (?:peux|peut) pas respirer|du mal [aà] respirer|difficult[eé] [aà] respirer|essouffl[eé]\w*|"
    r"glyc[eé]mie tr[eè]s basse|haleine fruit[eé]e)",
    r"\bpoitrine\b.{0,30}\b(?:douleur|mal|serrement|oppression|pression)\b",
    r"\b(?:douleur|mal|serrement|oppression|pression)\b.{0,30}\bpoitrine\b|douleur thoracique",
    # de-DE
    r"\b(?:bewusstlos\w*|ohnm[aä]chtig\w*|ohnmacht|umgekippt|zusammengebrochen|krampfanf[aä]ll\w*|epileptisch\w* anfall|"
    r"wacht nicht (?:mehr )?auf|nicht ansprechbar|reagiert nicht|kann nicht (?:mehr )?atmen|bekomme? keine luft|"
    r"atemnot|schwer atmen|sehr niedriger (?:blut)?zucker|(?:blut)?zucker (?:ist )?sehr niedrig|fruchtiger atem)\b",
    r"brust.{0,30}(?:schmerz|druck|enge|stechen)|\b(?:schmerz\w*|druck|enge|stechen)\b.{0,30}\bbrust",
    # it-IT
    r"\b(?:incosciente|svenut[oa]|svenimento|sviene|perso i sensi|perdita di coscienza|convulsion\w*|crisi epilettica|"
    r"non si sveglia|non risponde|non riesco a respirare|non respira|difficolt[aà] a respirare|fiato corto|"
    r"mi manca il respiro|(?:zucchero|glicemia) molto bass[oa]|alito fruttato)\b",
    r"\bpetto\b.{0,30}\b(?:dolore|male|pressione|oppressione)\b",
    r"\b(?:dolore|male|pressione|oppressione|fitta)\b.{0,30}\bpetto\b|dolore toracico",
    # ja-JP
    r"意識(?:が)?(?:ない|を失|がな|不明|がもうろう)|気を失|失神|倒れ|けいれん|痙攣|ひきつけ|"
    r"(?:呼びかけ|呼んで)(?:に|も)(?:反応|応答)(?:が)?(?:ない|しない)|起きない|目を覚まさない|息ができない|"
    r"呼吸ができない|息苦し|呼吸が苦し|血糖(?:値)?が(?:すごく|とても|非常に)低",
    r"胸.{0,10}(?:痛|圧迫|締め付け)|胸痛",
]

# Low-glucose symptom groups. Trembling alone is enough; otherwise two different groups are
# needed (sweating after a walk is not an emergency, sweating + dizziness may be).
LOW_SYMPTOMS: dict[str, list[str]] = {
    "tremor": [r"\bshak(?:y|ing|es)\b", r"\btrembl\w*", r"\bjitter\w*", r"\bk(?:aa|a)np\w*", r"\bkamp(?:ne|na|ta|ti|te|n)\w*",
               r"\btembl\w*", r"\btemblor\w*", r"\bzitter\w*", r"\bzittrig\w*",
               r"\btrem(?:o|ore|ori|ante|anti|are|ando|olio|a)\b", r"震え|震える|ふるえ|手が震"],
    "sweat": [r"\bsweat\w*", r"\bclammy\b", r"\bpas(?:ee|i)n\w*", r"\bsud(?:o|ando|ores|or)\b", r"\bsudor\w*",
              r"\bsueurs?\b", r"\btranspir\w*", r"\bmoite\b", r"\bschwitz\w*", r"\bschwei(?:ß|ss)\w*",
              r"\bsud(?:ato|ata|ati|ate|orazione)\b", r"冷や汗|汗"],
    "dizzy": [r"\bdizz\w*", r"light.?headed", r"\bgiddy\b", r"\bchakk?ar\b", r"\bmare(?:o|ad[oa]|os)\b", r"v[eé]rtigo",
              r"\bvertiges?\b", r"[eé]tourdi\w*", r"t[eê]te qui tourne", r"\bschwind\w*", r"\bbenommen\b",
              r"\bvertigin\w*", r"\bcapogiro\b", r"giramento di testa", r"\bstordit\w*", r"めまい|目まい|眩暈|ふらふら|ふらつ"],
    "confused": [r"\bconfus\w*", r"\bdisorient\w*", r"\bnot making sense\b", r"\bconfundid\w*", r"\bdesorientad\w*",
                 r"\bd[eé]sorient\w*", r"\bverwirrt\w*", r"\bdesorientiert\b", r"混乱|もうろう"],
    "palpitation": [r"heart (?:is )?(?:pounding|racing|beating fast)", r"\bpalpita\w*", r"\bghabrahat\b",
                    r"coraz[oó]n (?:acelerado|(?:me )?late (?:muy )?r[aá]pido)",
                    r"c(?:œ|oe)ur (?:qui )?(?:bat (?:tr[eè]s )?vite|s'emballe)", r"herzrasen|herzklopfen",
                    r"cuore (?:che )?batte (?:forte|veloce)|tachicardia", r"動悸|ドキドキ|どきどき"],
    "weak": [r"\bweak(?:ness)?\b", r"\bblurr\w*", r"\bkamzori\b", r"\bd[eé]bil\b", r"\bdebilidad\b",
             r"visi[oó]n borrosa", r"\bfaiblesse\b", r"vision floue|vue trouble", r"\bschwach\b", r"schw[aä]che",
             r"verschwommen", r"\bdebole\b", r"\bdebolezza\b", r"vista (?:offuscata|annebbiata)",
             r"脱力|力が入らない|目がかすむ|かすんで"],
    "crash": [r"sugar (?:has |is |just )?(?:crash|dropp|fell|falling|going down fast)\w*",
              r"(?:az[uú]car|glucosa) .{0,12}(?:baj[oó] (?:de golpe|mucho|r[aá]pido)|cay[oó]|cayendo|desplom\w*)",
              r"(?:glyc[eé]mie|sucre) .{0,12}(?:chut\w*|baisse (?:vite|rapidement)|d[eé]gringol\w*|s'effondr\w*)",
              r"zucker .{0,12}(?:abgest[uü]rzt|st[uü]rzt|f[aä]llt (?:schnell|stark)|sackt ab|abgesackt)",
              r"(?:glicemia|zucchero) .{0,12}(?:crollat\w*|crolla|scesa (?:di colpo|velocemente)|"
              r"scende (?:velocemente|rapidamente)|precipitat\w*)",
              r"血糖(?:値)?が.{0,6}(?:急に下が|急降下|急激に下が)"],
}
SINGLE_LOW_GROUPS = ("tremor",)
# Very-high-glucose danger signs (with a value > 400): vomiting, breathing, ketones, drowsiness.
HIGH_SYMPTOMS = [
    r"\bvomit\w*", r"\bthrowing up\b", r"\bulti\b", r"\bbreath\w*", r"\bsaa?ns\b", r"\bketon\w*", r"\bdrows\w*",
    r"\bsleepy\b", r"\bconfus\w*",
    r"\bv[oó]mit\w*", r"\bn[aá]use\w*", r"\brespir\w*", r"\bceton\w*", r"\bsomnolen\w*", r"\badormilad\w*",
    r"\bvomi\w*", r"\bnaus[eé]e\w*", r"\bc[eé]ton\w*", r"\bendormi\w*",
    r"\berbrech\w*", r"[uü]bergeb\w*", r"[uü]belkeit", r"\batm\w*", r"\bketon\w*", r"schl[aä]frig", r"\bbenommen\b",
    r"\bnausea\b", r"\bchetoni\w*", r"\bsonnolen\w*", r"\bassonnat\w*",
    r"吐|嘔吐|吐き気|息|呼吸|ケトン|眠い|眠気|ぼんやり",
]

# ----------------------------------------------------------------------------- reported glucose values
# A glucose value the user reports: a number after a sugar/glucose/reading/meter word (up to ~25
# characters apart: "mi glucosa ahora es 172"), a number with mg/dL or mmol/L, or a bare number.
GLUCOSE_WORDS = (r"(?:blood sugar|sugar|glucose|readings?|meter|glucometer|bsl|fbs|ppbs|rbs|"
                 r"glucosa|glucemia|az[uú]car|gluc[oó]metro|medici[oó]n|"
                 r"glyc[eé]mie|sucre|glucom[eè]tre|lecteur|"
                 r"blutzucker|zucker|zuckerwert|glukose|messger[aä]t|messwert|\bwert\b|"
                 r"glicemia|glucosio|zucchero|glucometro|misurazione|valore|"
                 r"血糖値|血糖|グルコース|測定値)")
# Numbers: a decimal comma is allowed ("7,2"); it only counts with an explicit unit (see _to_mgdl).
_NUM = r"(\d{2,3}(?:[.,]\d+)?|\d[.,]\d+)"
_NOT_A_READING_BEFORE = re.compile(
    r"(above|over|than|between|cross|exceed|target|range|reach|go to|goes to|hit|from|upto|up to|by|"
    r"times|out of|in \d|ke paar|se upar|"
    r"encima|m[aá]s de|menos de|entre|super|pasar de|hasta|llegar a|en \d|de cada|objetivo|rango|"
    r"dessus|plus de|moins de|d[eé]pass|jusqu|atteindre|dans \d|sur|cible|"
    r"[uü]ber|unter|mehr als|weniger als|zwischen|\bbis\b|erreich|ziel|"
    r"sopra|oltre|pi[uù] di|meno di|\btra\b|\bfra\b|fino a|arrivare a|obiettivo)", re.I)
_NOT_A_READING_AFTER = re.compile(
    r"^\s*(?:[-–]\s*\d|to\s+\d|:\d|min\b|mins\b|minutes?\b|hrs?\b|hours?\b|days?\b|weeks?\b|months?\b|years?\b|"
    r"%|percent|g\b|gm\b|grams?\b|kg\b|steps?\b|k?cal\b|times\b|out of|or (?:more|less)|plus\b|\+|cross|"
    r"minutos?\b|horas?\b|d[ií]as?\b|semanas?\b|mes(?:es)?\b|a[nñ]os?\b|por ciento|gramos?\b|veces\b|pasos\b|a\s+\d|"
    r"o (?:m[aá]s|menos)|"
    r"minutes?\b|heures?\b|jours?\b|semaines?\b|mois\b|ans?\b|ann[eé]es?\b|pour ?cent|grammes?\b|fois\b|pas\b|"
    r"[aà]\s+\d|ou (?:plus|moins)|"
    r"minuten?\b|stunden?\b|tagen?\b|tage\b|wochen?\b|monaten?\b|monate\b|jahren?\b|jahre\b|prozent|gramm\b|mal\b|"
    r"schritte\b|bis\s+\d|oder (?:mehr|weniger)|"
    r"minut[oi]\b|ore\b|giorn[oi]\b|settiman[ae]\b|mes[ei]\b|ann[oi]\b|per ?cento|gramm[oi]\b|volte\b|passi\b|"
    r"o (?:pi[uù]|meno)|"
    r"を超|以上|以下|未満|より|を下回|を上回|まで|分|時間|日|週|か月|ヶ月|カ月|年|パーセント|グラム|回|歩|キロ|〜\s*\d|~\s*\d)",
    re.I)

DIAGNOSIS_PATTERNS = [
    r"\b(do i have|diagnose|is it cancer|am i diabetic|do i have (?:kidney|heart)|what disease)\b",
    # es-ES (a statement such as "tengo diabetes tipo 2" is context, not a diagnosis request)
    r"¿\s*tengo (?:una? )?(?:enfermedad|diabetes|c[aá]ncer|problemas? de (?:ri[nñ]\w*|coraz[oó]n))|"
    r"diagnostic(?:ar|arme|a|ame|que)\b|qu[eé] enfermedad tengo|¿\s*soy diab[eé]tic[oa]|\bes c[aá]ncer\b",
    # fr-FR
    r"est-ce que j'ai (?:une? )?(?:maladie|diab[eè]te|cancer|probl[eè]me)|ai-je (?:une? )?(?:maladie|diab[eè]te|cancer|"
    r"probl[eè]me)|(?:me |pouvez-vous |peux-tu )diagnostiquer|diagnostiquez-moi|quelle maladie|suis-je diab[eé]tique|"
    r"c'est un cancer",
    # de-DE
    r"habe ich (?:eine? )?(?:\w*krankheit|\w*erkrankung|diabetes|krebs)|bin ich (?:zucker)?krank|bin ich diabetiker|"
    r"(?:kannst du|k[oö]nnen sie|koennen sie) mich diagnostizieren|diagnostizier(?:e|en sie) mich|welche krankheit|"
    r"ist (?:es|das) krebs",
    # it-IT (statement vs question differ only by "?")
    r"\bho (?:il |la |una? |l')?(?:\w*malattia|diabete|cancro|tumore)\b[^.!?]*\?|(?:mi )?(?:puoi|pu[oò]) diagnosticar\w*|"
    r"diagnosticami|mi fa(?:i)? una diagnosi|che malattia|quale malattia|sono diabetic[oa]\s*\?|[eè] un cancro",
    # ja-JP
    r"(?:病気|糖尿病|がん|癌|腎臓病|心臓病)(?:です|でしょう)か|診断して|診断でき|何の病気|どんな病気|病気かどうか",
]
INJECTION_PATTERNS = [
    r"ignore (?:all |the |your )?(?:previous |above |prior )?(?:instructions|prompts?|rules)",
    r"(system prompt|you are now|disregard (?:your|the|all) (?:rules|instructions)|developer mode|jailbreak|act as)",
    r"(tell (?:the user|me) to (?:take|double|stop)|recommend (?:a |an )?(?:dose|insulin))",
    # "note to the AI / assistant" and "from now on answer ..." smuggled into a meal description
    r"\b(note (?:to|for) (?:the )?(?:ai|assistant|bot|model)|(?:ai|assistant)\s*:|from now on (?:answer|reply|say|you))\b",
    # es-ES / it-IT: "ignora (todas) las instrucciones (anteriores)", "ignora le istruzioni"
    r"\bignora\w* (?:todas |tutte )?(?:las |le |tus |tue |mis )*(?:instrucciones|reglas|istruzioni|regole)",
    r"\bolvida (?:todas )?(?:las |tus )?(?:instrucciones|reglas)|haz caso omiso de (?:las |tus )?(?:instrucciones|reglas)",
    r"prompt (?:del|de) sistema|\bahora eres (?:un|una|el|la)\b|a partir de ahora,? (?:responde|eres|di)\b|"
    r"nota para (?:la |el )?(?:ia|asistente|modelo)",
    # fr-FR
    r"\bignore[zr]? (?:toutes )?(?:les |tes |vos )?(?:instructions|consignes|r[eè]gles)",
    r"\boublie[zr]? (?:toutes )?(?:les |tes |vos )?(?:instructions|consignes|r[eè]gles)",
    r"prompt syst[eè]me|(?:tu es|vous [eê]tes) maintenant (?:un|une|le|la)\b|"
    r"[aà] partir de maintenant,? (?:r[eé]ponds|r[eé]pondez|tu es|dis)\b|note (?:pour|[aà]) (?:l'ia|l'assistant|le mod[eè]le)",
    # de-DE
    r"\bignorier\w* (?:alle |deine |ihre |die )*(?:vorherigen |bisherigen |obigen )?(?:anweisungen|regeln|instruktionen)",
    r"\bvergiss (?:alle )?(?:deine |vorherigen )?(?:anweisungen|regeln)",
    r"system-?prompt|\bdu bist (?:jetzt|ab jetzt) (?:ein|eine|der|die)\b|ab jetzt (?:antwortest du|bist du|sag)\b|"
    r"(?:hinweis|notiz) f[uü]r (?:die ki|den assistenten)",
    # it-IT
    r"\bdimentica (?:tutte )?(?:le )?(?:tue )?(?:istruzioni|regole)",
    r"prompt di sistema|\b(?:ora|adesso) sei (?:un|una|il|la)\b|d'ora in poi,? (?:rispondi|sei|di)\b|"
    r"nota per (?:l'ia|l'assistente|il modello)",
    # ja-JP
    r"(?:以前|前|これまで|上記|今まで)の(?:指示|命令|ルール|指令)を(?:すべて|全て)?(?:無視|忘れ)|指示を無視|"
    r"(?:ルール|指示|命令|制限)(?:は|を)(?:すべて|全て)?無視|"
    r"システムプロンプト|あなたは(?:今から|これから)|今からあなたは|これからは.{0,10}(?:答え|言っ)|"
    r"aiへの(?:メモ|指示)|アシスタントへの(?:メモ|指示)",
]

# ----------------------------------------------------------------------------- fixed messages
MESSAGES = {
    "dose": {
        "en-US": "I can't advise on insulin or medicine doses. Please ask your doctor before changing any medicine. I can show how food and walks change your glucose.",
        "es-ES": "No puedo aconsejarle sobre dosis de insulina ni de medicamentos. Consulte a su médico antes de cambiar cualquier medicamento. Puedo mostrarle cómo la comida y los paseos cambian su glucosa.",
        "fr-FR": "Je ne peux pas vous conseiller sur les doses d'insuline ou de médicaments. Demandez l'avis de votre médecin avant de modifier un médicament. Je peux vous montrer comment les repas et la marche modifient votre glycémie.",
        "de-DE": "Ich kann Sie nicht zu Insulin- oder Medikamentendosen beraten. Bitte fragen Sie Ihren Arzt oder Ihre Ärztin, bevor Sie ein Medikament ändern. Ich kann Ihnen zeigen, wie Mahlzeiten und Spaziergänge Ihren Blutzucker verändern.",
        "it-IT": "Non posso darle consigli sulle dosi di insulina o di farmaci. Chieda al suo medico prima di cambiare qualsiasi farmaco. Posso mostrarle come i pasti e le camminate cambiano la sua glicemia.",
        "ja-JP": "インスリンや薬の量についてはアドバイスできません。薬を変える前に、必ず主治医に相談してください。食事や散歩で血糖値がどう変わるかをお見せできます。",
    },
    "emergency": {
        "en-US": "This may be an emergency. Get medical help now: call your local emergency number or go to the nearest hospital. If you are awake and can swallow and think your sugar is low, take something sugary like juice. Do not stay alone.",
        "es-ES": "Esto puede ser una emergencia. Busque ayuda médica ahora: llame a su número local de emergencias o vaya al hospital más cercano. Si está consciente, puede tragar y cree que tiene la glucosa baja, tome algo azucarado, como un zumo. No se quede sin compañía.",
        "fr-FR": "Il peut s'agir d'une urgence. Obtenez de l'aide médicale maintenant : appelez le numéro d'urgence local ou rendez-vous à l'hôpital le plus proche. Si vous êtes conscient(e), pouvez avaler et pensez que votre glycémie est basse, prenez quelque chose de sucré, comme un jus de fruits. Ne restez pas seul(e).",
        "de-DE": "Das kann ein Notfall sein. Holen Sie sofort medizinische Hilfe: Rufen Sie Ihre örtliche Notrufnummer an oder gehen Sie ins nächste Krankenhaus. Wenn Sie wach sind, schlucken können und glauben, dass Ihr Blutzucker niedrig ist, nehmen Sie etwas Zuckerhaltiges wie Saft zu sich. Bleiben Sie nicht allein.",
        "it-IT": "Potrebbe essere un'emergenza. Chieda subito aiuto medico: chiami il numero di emergenza locale o vada all'ospedale più vicino. Se è cosciente, riesce a deglutire e pensa di avere la glicemia bassa, prenda qualcosa di zuccherato, come un succo di frutta. Si faccia stare vicino da qualcuno.",
        "ja-JP": "緊急事態の可能性があります。今すぐ医療の助けを求めてください。お住まいの地域の緊急通報番号に電話するか、最寄りの病院へ行ってください。意識があり、飲み込むことができ、血糖値が低いと思われる場合は、ジュースなど糖分のあるものをとってください。一人にならないでください。",
    },
    "diagnosis": {
        "en-US": "I can't diagnose illnesses. Please talk to your doctor about this. I can help you understand your glucose twin.",
        "es-ES": "No puedo diagnosticar enfermedades. Hable de esto con su médico. Puedo ayudarle a entender su gemelo digital de glucosa.",
        "fr-FR": "Je ne peux pas poser de diagnostic. Parlez-en à votre médecin. Je peux vous aider à comprendre votre jumeau numérique de glycémie.",
        "de-DE": "Ich kann keine Krankheiten diagnostizieren. Bitte sprechen Sie darüber mit Ihrem Arzt oder Ihrer Ärztin. Ich kann Ihnen helfen, Ihren digitalen Zwilling zu verstehen.",
        "it-IT": "Non posso diagnosticare malattie. Ne parli con il suo medico. Posso aiutarla a capire il suo gemello digitale della glicemia.",
        "ja-JP": "病気の診断はできません。この件は主治医に相談してください。血糖値のデジタルツインを理解するお手伝いはできます。",
    },
    "out_of_scope": {
        "en-US": "I can only help with your glucose twin: forecasts, meals, walks and when to check. For anything else, please ask someone else.",
        "es-ES": "Solo puedo ayudarle con su gemelo digital de glucosa: pronósticos, comidas, paseos y cuándo medirse. Para cualquier otra cosa, consulte otra fuente.",
        "fr-FR": "Je peux seulement vous aider avec votre jumeau numérique de glycémie : prévisions, repas, marche et moment des mesures. Pour toute autre question, adressez-vous à une autre source.",
        "de-DE": "Ich kann Ihnen nur bei Ihrem digitalen Zwilling helfen: Prognosen, Mahlzeiten, Spaziergänge und wann Sie messen sollten. Für alles andere wenden Sie sich bitte an eine andere Stelle.",
        "it-IT": "Posso aiutarla solo con il suo gemello digitale: previsioni, pasti, camminate e quando misurare. Per tutto il resto, si rivolga a un'altra fonte.",
        "ja-JP": "お手伝いできるのは、あなたの血糖値のデジタルツインに関すること（予測、食事、散歩、測定のタイミング）だけです。それ以外のことは、ほかの情報源にお尋ねください。",
    },
    "hypo": {
        "en-US": "A reading of {value} is low (below 70). Take something sugary now, like half a glass of fruit juice or a spoonful of sugar in water, and check again in 15 minutes. If it stays low or you feel unwell, call your local emergency number. Please tell your doctor about low readings.",
        "es-ES": "Una medición de {value} es baja (por debajo de 70). Tome ahora algo azucarado, como medio vaso de zumo de fruta o una cucharada de azúcar en agua, y vuelva a medirse en 15 minutos. Si sigue baja o se encuentra mal, llame a su número local de emergencias. Informe a su médico de las mediciones bajas.",
        "fr-FR": "Une mesure de {value} est basse (en dessous de 70). Prenez maintenant quelque chose de sucré, comme un demi-verre de jus de fruits ou une cuillerée de sucre dans de l'eau, et refaites une mesure dans 15 minutes. Si elle reste basse ou si vous ne vous sentez pas bien, appelez le numéro d'urgence local. Signalez les mesures basses à votre médecin.",
        "de-DE": "Ein Messwert von {value} ist niedrig (unter 70). Nehmen Sie jetzt etwas Zuckerhaltiges zu sich, zum Beispiel ein halbes Glas Fruchtsaft oder einen Löffel Zucker in Wasser, und messen Sie nach 15 Minuten erneut. Wenn der Wert niedrig bleibt oder Sie sich unwohl fühlen, rufen Sie Ihre örtliche Notrufnummer an. Bitte informieren Sie Ihren Arzt oder Ihre Ärztin über niedrige Messwerte.",
        "it-IT": "Una misurazione di {value} è bassa (sotto 70). Prenda subito qualcosa di zuccherato, come mezzo bicchiere di succo di frutta o un cucchiaio di zucchero in acqua, e misuri di nuovo dopo 15 minuti. Se resta bassa o non si sente bene, chiami il numero di emergenza locale. Informi il suo medico delle misurazioni basse.",
        "ja-JP": "{value}という測定値は低い値です（70未満）。今すぐ、コップ半分の果汁ジュースや水に溶かしたスプーン一杯の砂糖など、糖分のあるものをとり、15分後にもう一度測ってください。低いままの場合や気分が悪い場合は、お住まいの地域の緊急通報番号に電話してください。低い測定値が出たことを主治医に伝えてください。",
    },
    "hyper": {
        "en-US": "A reading of {value} is very high. Drink some water, check again in a while, and test for ketones if you can. If it stays above 300, or you have vomiting, trouble breathing or drowsiness, call your local emergency number or see a doctor today. Do not change any medicine without your doctor.",
        "es-ES": "Una medición de {value} es muy alta. Beba algo de agua, vuelva a medirse dentro de un rato y, si puede, mida las cetonas. Si sigue por encima de 300, o tiene vómitos, dificultad para respirar o somnolencia, llame a su número local de emergencias o acuda hoy a un médico. No cambie ningún medicamento sin consultar a su médico.",
        "fr-FR": "Une mesure de {value} est très élevée. Buvez un peu d'eau, refaites une mesure un peu plus tard et recherchez des cétones si vous le pouvez. Si elle reste au-dessus de 300, ou si vous avez des vomissements, du mal à respirer ou une somnolence, appelez le numéro d'urgence local ou consultez un médecin aujourd'hui. Ne modifiez aucun médicament sans l'avis de votre médecin.",
        "de-DE": "Ein Messwert von {value} ist sehr hoch. Trinken Sie etwas Wasser, messen Sie nach einer Weile erneut und testen Sie, wenn möglich, auf Ketone. Wenn der Wert über 300 bleibt oder Sie erbrechen, schwer atmen oder sehr schläfrig sind, rufen Sie Ihre örtliche Notrufnummer an oder gehen Sie heute noch zu einem Arzt. Ändern Sie kein Medikament ohne Rücksprache mit Ihrem Arzt.",
        "it-IT": "Una misurazione di {value} è molto alta. Beva un po' d'acqua, misuri di nuovo tra un po' e, se può, controlli i chetoni. Se resta sopra 300, o se ha vomito, difficoltà a respirare o sonnolenza, chiami il numero di emergenza locale o si faccia visitare da un medico oggi stesso. Non cambi nessun farmaco senza il suo medico.",
        "ja-JP": "{value}という測定値はとても高い値です。水を飲み、しばらくしてからもう一度測り、可能であればケトン体を調べてください。300を超えたままの場合や、嘔吐、息苦しさ、強い眠気がある場合は、お住まいの地域の緊急通報番号に電話するか、今日中に医師の診察を受けてください。主治医に相談せずに薬を変えないでください。",
    },
    "reading_noted": {
        "en-US": "I have added this reading to your twin.",
        "es-ES": "He añadido esta medición a su gemelo digital.",
        "fr-FR": "J'ai ajouté cette mesure à votre jumeau numérique.",
        "de-DE": "Ich habe diesen Messwert zu Ihrem digitalen Zwilling hinzugefügt.",
        "it-IT": "Ho aggiunto questa misurazione al suo gemello digitale.",
        "ja-JP": "この測定値をあなたのデジタルツインに追加しました。",
    },
    "reading_pending": {
        "en-US": "Confirm below if you want me to add this reading to your twin.",
        "es-ES": "Confirme abajo si quiere que añada esta medición a su gemelo digital.",
        "fr-FR": "Confirmez ci-dessous si vous voulez que j'ajoute cette mesure à votre jumeau numérique.",
        "de-DE": "Bestätigen Sie unten, wenn ich diesen Messwert zu Ihrem digitalen Zwilling hinzufügen soll.",
        "it-IT": "Confermi qui sotto se vuole che aggiunga questa misurazione al suo gemello digitale.",
        "ja-JP": "この測定値をデジタルツインに追加する場合は、下で確認してください。",
    },
    "high": {
        "en-US": "A reading of {value} is high (above 250). Drink some water, avoid sugary food and drinks, and check again in 2 to 4 hours. If your readings stay above 250, tell your doctor.",
        "es-ES": "Una medición de {value} es alta (por encima de 250). Beba algo de agua, evite comidas y bebidas azucaradas, y vuelva a medirse dentro de 2 a 4 horas. Si sus mediciones siguen por encima de 250, informe a su médico.",
        "fr-FR": "Une mesure de {value} est élevée (au-dessus de 250). Buvez un peu d'eau, évitez les aliments et boissons sucrés, et refaites une mesure dans 2 à 4 heures. Si vos mesures restent au-dessus de 250, parlez-en à votre médecin.",
        "de-DE": "Ein Messwert von {value} ist hoch (über 250). Trinken Sie etwas Wasser, meiden Sie zuckerhaltige Speisen und Getränke und messen Sie in 2 bis 4 Stunden erneut. Wenn Ihre Messwerte über 250 bleiben, sagen Sie es Ihrem Arzt oder Ihrer Ärztin.",
        "it-IT": "Una misurazione di {value} è alta (sopra 250). Beva un po' d'acqua, eviti cibi e bevande zuccherati e misuri di nuovo tra 2 e 4 ore. Se le misurazioni restano sopra 250, lo dica al suo medico.",
        "ja-JP": "{value}という測定値は高い値です（250超）。水を飲み、糖分の多い食べ物や飲み物を避け、2〜4時間後にもう一度測ってください。測定値が250を超えたままの場合は、主治医に伝えてください。",
    },
    "ok": {
        "en-US": "No urgent action is needed for this reading.",
        "es-ES": "Esta medición no requiere ninguna acción urgente.",
        "fr-FR": "Cette mesure ne nécessite aucune action urgente.",
        "de-DE": "Für diesen Messwert ist keine dringende Maßnahme nötig.",
        "it-IT": "Per questa misurazione non serve nessuna azione urgente.",
        "ja-JP": "この測定値について、急いで対応する必要はありません。",
    },
}

# Titles and short action lists of the shared reading-safety policy (``assess_reading``), per level.
READING_TITLES = {
    "ok": {"en-US": "Reading recorded", "es-ES": "Medición registrada", "fr-FR": "Mesure enregistrée",
           "de-DE": "Messwert gespeichert", "it-IT": "Misurazione registrata", "ja-JP": "測定値を記録しました"},
    "low": {"en-US": "Low glucose", "es-ES": "Glucosa baja", "fr-FR": "Glycémie basse", "de-DE": "Niedriger Blutzucker",
            "it-IT": "Glicemia bassa", "ja-JP": "低血糖"},
    "very_low": {"en-US": "Very low glucose: possible emergency", "es-ES": "Glucosa muy baja: posible emergencia",
                 "fr-FR": "Glycémie très basse : urgence possible", "de-DE": "Sehr niedriger Blutzucker: möglicher Notfall",
                 "it-IT": "Glicemia molto bassa: possibile emergenza", "ja-JP": "非常に低い血糖値：緊急の可能性"},
    "high": {"en-US": "High glucose", "es-ES": "Glucosa alta", "fr-FR": "Glycémie élevée", "de-DE": "Hoher Blutzucker",
             "it-IT": "Glicemia alta", "ja-JP": "高血糖"},
    "very_high": {"en-US": "Very high glucose", "es-ES": "Glucosa muy alta", "fr-FR": "Glycémie très élevée",
                  "de-DE": "Sehr hoher Blutzucker", "it-IT": "Glicemia molto alta", "ja-JP": "非常に高い血糖値"},
    "emergency": {"en-US": "Possible emergency", "es-ES": "Posible emergencia", "fr-FR": "Urgence possible",
                  "de-DE": "Möglicher Notfall", "it-IT": "Possibile emergenza", "ja-JP": "緊急の可能性"},
}
READING_ACTIONS = {
    "low": {
        "en-US": ["Take something sugary now (half a glass of juice or a spoonful of sugar in water)",
                  "Check again in 15 minutes", "Call your local emergency number if it stays low or you feel unwell"],
        "es-ES": ["Tome ahora algo azucarado (medio vaso de zumo o una cucharada de azúcar en agua)",
                  "Vuelva a medirse en 15 minutos", "Llame a su número local de emergencias si sigue baja o se encuentra mal"],
        "fr-FR": ["Prenez maintenant quelque chose de sucré (un demi-verre de jus ou une cuillerée de sucre dans de l'eau)",
                  "Refaites une mesure dans 15 minutes",
                  "Appelez le numéro d'urgence local si elle reste basse ou si vous ne vous sentez pas bien"],
        "de-DE": ["Nehmen Sie jetzt etwas Zuckerhaltiges zu sich (ein halbes Glas Saft oder einen Löffel Zucker in Wasser)",
                  "Messen Sie nach 15 Minuten erneut",
                  "Rufen Sie Ihre örtliche Notrufnummer an, wenn der Wert niedrig bleibt oder Sie sich unwohl fühlen"],
        "it-IT": ["Prenda subito qualcosa di zuccherato (mezzo bicchiere di succo o un cucchiaio di zucchero in acqua)",
                  "Misuri di nuovo dopo 15 minuti",
                  "Chiami il numero di emergenza locale se resta bassa o non si sente bene"],
        "ja-JP": ["今すぐ糖分のあるものをとってください（コップ半分のジュース、または水に溶かしたスプーン一杯の砂糖）",
                  "15分後にもう一度測ってください", "低いままの場合や気分が悪い場合は、お住まいの地域の緊急通報番号に電話してください"],
    },
    "emergency": {
        "en-US": ["Call your local emergency number or go to the nearest hospital now",
                  "If awake and able to swallow, take something sugary", "Do not stay alone"],
        "es-ES": ["Llame ahora a su número local de emergencias o vaya al hospital más cercano",
                  "Si está consciente y puede tragar, tome algo azucarado", "No se quede sin compañía"],
        "fr-FR": ["Appelez maintenant le numéro d'urgence local ou rendez-vous à l'hôpital le plus proche",
                  "Si vous êtes conscient(e) et pouvez avaler, prenez quelque chose de sucré", "Ne restez pas seul(e)"],
        "de-DE": ["Rufen Sie jetzt Ihre örtliche Notrufnummer an oder gehen Sie ins nächste Krankenhaus",
                  "Wenn Sie wach sind und schlucken können, nehmen Sie etwas Zuckerhaltiges zu sich",
                  "Bleiben Sie nicht allein"],
        "it-IT": ["Chiami subito il numero di emergenza locale o vada all'ospedale più vicino",
                  "Se è cosciente e riesce a deglutire, prenda qualcosa di zuccherato", "Si faccia stare vicino da qualcuno"],
        "ja-JP": ["今すぐお住まいの地域の緊急通報番号に電話するか、最寄りの病院へ行ってください",
                  "意識があり飲み込める場合は、糖分のあるものをとってください", "一人にならないでください"],
    },
    "high": {
        "en-US": ["Drink some water", "Check again in 2 to 4 hours", "Tell your doctor if it stays above 250"],
        "es-ES": ["Beba algo de agua", "Vuelva a medirse dentro de 2 a 4 horas",
                  "Informe a su médico si sigue por encima de 250"],
        "fr-FR": ["Buvez un peu d'eau", "Refaites une mesure dans 2 à 4 heures",
                  "Parlez-en à votre médecin si elle reste au-dessus de 250"],
        "de-DE": ["Trinken Sie etwas Wasser", "Messen Sie in 2 bis 4 Stunden erneut",
                  "Sagen Sie es Ihrem Arzt oder Ihrer Ärztin, wenn der Wert über 250 bleibt"],
        "it-IT": ["Beva un po' d'acqua", "Misuri di nuovo tra 2 e 4 ore", "Lo dica al suo medico se resta sopra 250"],
        "ja-JP": ["水を飲んでください", "2〜4時間後にもう一度測ってください", "250を超えたままの場合は主治医に伝えてください"],
    },
    "very_high": {
        "en-US": ["Drink some water", "Test for ketones if you can",
                  "Call your local emergency number or see a doctor today if you are vomiting, breathless or drowsy"],
        "es-ES": ["Beba algo de agua", "Si puede, mida las cetonas",
                  "Llame a su número local de emergencias o acuda hoy a un médico si tiene vómitos, le falta el aire o tiene somnolencia"],
        "fr-FR": ["Buvez un peu d'eau", "Recherchez des cétones si vous le pouvez",
                  "Appelez le numéro d'urgence local ou consultez un médecin aujourd'hui en cas de vomissements, d'essoufflement ou de somnolence"],
        "de-DE": ["Trinken Sie etwas Wasser", "Testen Sie, wenn möglich, auf Ketone",
                  "Rufen Sie Ihre örtliche Notrufnummer an oder gehen Sie heute noch zu einem Arzt, wenn Sie erbrechen, kurzatmig oder sehr schläfrig sind"],
        "it-IT": ["Beva un po' d'acqua", "Se può, controlli i chetoni",
                  "Chiami il numero di emergenza locale o si faccia visitare da un medico oggi stesso se ha vomito, fiato corto o sonnolenza"],
        "ja-JP": ["水を飲んでください", "可能であればケトン体を調べてください",
                  "嘔吐、息苦しさ、強い眠気がある場合は、お住まいの地域の緊急通報番号に電話するか、今日中に医師の診察を受けてください"],
    },
}

# Reading levels of the shared policy (International Consensus / ADA glucose levels):
# level 2 hypoglycaemia < 54, level 1 < 70; level 2 hyperglycaemia > 250; > 300 very high (ketone check).
VERY_LOW_BELOW = 54.0
LOW_BELOW = 70.0
HIGH_ABOVE = 250.0
VERY_HIGH_ABOVE = 300.0


def _norm(s: str, lower: bool = True) -> str:
    """NFKC (full-width Japanese digits / letters -> ASCII, half-width katakana -> full-width),
    typographic apostrophes -> ', lower case.

    Patterns are normalised with ``lower=False`` (lowercasing would turn ``\\S`` into ``\\s``)."""
    t = unicodedata.normalize("NFKC", s.lower() if lower else s)
    t = t.replace("’", "'").replace("‘", "'")
    return normalise_digits(t)


@lru_cache(maxsize=512)
def _compiled(p: str) -> re.Pattern[str]:
    return re.compile(_norm(p, lower=False), re.I)


def _any(patterns: list[str], text: str, normalised: bool = False) -> bool:
    t = text if normalised else _norm(text)
    return any(_compiled(p).search(t) for p in patterns)


_NUM_RE = re.compile(r"(?<![\d.:,/])" + _NUM + r"(?![\d.,/]\d)")
_WORD_RE = re.compile(GLUCOSE_WORDS, re.I)
_UNIT_AFTER = re.compile(r"^\s*(mg\s*/?\s*dl|mgdl|mg%|mmol)", re.I)
_BARE = re.compile(r"^\s*(?:it'?s|its|is|es|est|ist|è|e)?\s*" + _NUM
                   + r"\s*(?:mg\s*/?\s*dl|mgdl|mmol(?:\s*/\s*l)?)?\s*(?:です)?\s*[.!?。]?\s*$", re.I)


def glucose_values(text: str) -> list[float]:
    """Glucose values (mg/dL) the user reports in ``text``, in order.

    Counted: a number with mg/dL or mmol/L after it; a number up to ~25 characters after a
    sugar / glucose / reading / meter word in any release language (but not "above 180",
    "in 30 minutes", "70 to 180", "por encima de 180", "180を超え" ...); a message that is only a
    number. mmol/L values (with the unit, or a decimal POINT below 35) are converted (x 18).
    A decimal COMMA ("7,2") counts only with an explicit unit ("7,2 mmol/L" = 7.2 mmol/L): without
    one it is ambiguous, so it is not parsed and the app asks."""
    t = _norm(text)
    bare = _BARE.match(t)
    if bare:
        v0 = _to_mgdl(bare.group(1), t[bare.end(1):])
        return [v0] if v0 is not None else []
    out: list[float] = []
    for m in _NUM_RE.finditer(t):
        after = t[m.end():m.end() + 30]
        if _UNIT_AFTER.match(after):
            v = _to_mgdl(m.group(1), after)
        else:
            if _NOT_A_READING_AFTER.match(after):
                continue
            window = t[max(0, m.start() - 40):m.start()]
            words = list(_WORD_RE.finditer(window))
            if not words:
                continue
            gap = window[words[-1].end():]
            if len(gap) > 25 or re.search(r"[\d\n]", gap) or _NOT_A_READING_BEFORE.search(gap):
                continue
            v = _to_mgdl(m.group(1), after)
        if v is not None:
            out.append(v)
    return out


def _to_mgdl(num: str, context: str) -> float | None:
    unit = _UNIT_AFTER.match(context)
    if "," in num:
        if not unit:
            return None  # "7,2" without a unit: ambiguous, never guessed
        num = num.replace(",", ".")
    v = float(num)
    if "mmol" in context[:12] or ("." in num and v < 35 and not (unit and "mg" in unit.group(1))):
        v = round(v * 18.0, 0)
    return v if 20 <= v <= 700 else None


def _low_groups(t: str) -> set[str]:
    return {g for g, pats in LOW_SYMPTOMS.items() if _any(pats, t, normalised=True)}


@dataclass
class Assessment:
    """Deterministic safety verdict for one user message (rules only, before any LLM)."""

    kind: str | None = None          # "emergency" | "dose" | "diagnosis" | None
    reason: str | None = None        # why (e.g. "glucose_below_54", "low_with_symptoms", "symptoms")
    glucose: float | None = None     # first reported glucose value (mg/dL), if any
    glycaemia: str | None = None     # "hypo" (< 70) | "hyper" (> 250) | None
    values: list[float] = field(default_factory=list)


def assess(text: str, use_values: bool = True) -> Assessment:
    """Emergency first (reported values + symptoms), then dose, then diagnosis.

    * any reported glucose < 54, or < 70 with a low-sugar symptom, or > 400 with vomiting /
      breathing / ketone / drowsiness words -> emergency;
    * severe symptoms alone (fainting, seizure, chest pain, can't breathe, trembling, or two
      different low-sugar symptoms such as sweating + dizziness) -> emergency;
    * otherwise a reading < 70 or > 250 is flagged as ``glycaemia`` so the agent always shows the
      shared reading-safety message (``assess_reading``) with it.

    ``use_values=False`` ignores numbers (for prompt-injection text, whose numbers are not readings)."""
    t = _norm(text)
    vals = glucose_values(text) if use_values else []
    g = vals[0] if vals else None
    a = Assessment(glucose=g, values=vals)
    low = _low_groups(t)
    if any(v < 54 for v in vals):
        a.kind, a.reason = "emergency", "glucose_below_54"
    elif any(v < 70 for v in vals) and low:
        a.kind, a.reason = "emergency", "low_with_symptoms"
    elif any(v > 400 for v in vals) and _any(HIGH_SYMPTOMS, t, normalised=True):
        a.kind, a.reason = "emergency", "high_with_symptoms"
    elif _any(EMERGENCY_PATTERNS, t, normalised=True):
        a.kind, a.reason = "emergency", "symptoms"
    elif low & set(SINGLE_LOW_GROUPS) or len(low) >= 2:
        a.kind, a.reason = "emergency", "low_symptoms"
    elif _any(DOSE_PATTERNS, t, normalised=True):
        a.kind, a.reason = "dose", "dose"
    elif _any(DIAGNOSIS_PATTERNS, t, normalised=True):
        a.kind, a.reason = "diagnosis", "diagnosis"
    if vals:
        lo, hi = min(vals), max(vals)
        a.glycaemia = "hypo" if lo < LOW_BELOW else "hyper" if hi > HIGH_ABOVE else None
    return a


def classify(text: str) -> str | None:
    """Return 'emergency' | 'dose' | 'diagnosis' | None (rules only, run before any LLM)."""
    return assess(text).kind


def is_injection(text: str) -> bool:
    return _any(INJECTION_PATTERNS, text)


# ----------------------------------------------------------------------------- output policy
# Constrained medication policy for GENERATED text (LLM drafts): medication content may appear only
# in the fixed, reviewed sentences of this module (e.g. "Do not change any medicine without your
# doctor."). Any other mention of a medicine, insulin, a dose or a dose-like amount - in any release
# language (or romanised Hindi / Bengali / Kannada), negated or not - makes the draft unsafe, and the
# agent falls back to a deterministic template.
MED_TERMS = [
    # English drug names (generic / brands) and generic medication words
    r"\b(?:insulin\w*|insul[ie]n|inslin|metformin\w*|glycomet|glucophage|glimepiride|amaryl|gliclazide|glipizide|"
    r"glibenclamide|sulfonylureas?|sitagliptin|januvia|vildagliptin|galvus|teneligliptin|linagliptin|"
    r"empagliflozin|jardiance|dapagliflozin|forxiga|canagliflozin|pioglitazone|acarbose|voglibose|semaglutide|"
    r"ozempic|rybelsus|wegovy|liraglutide|dulaglutide|trulicity|tirzepatide|mounjaro|lantus|levemir|tresiba|"
    r"basalog|glargine|degludec|novorapid|humalog|humulin|mixtard|actrapid|ryzodeg|statins?|atorvastatin|"
    r"rosuvastatin|telmisartan|amlodipine|aspirin)\b",
    r"\b(?:medicines?|medications?|meds|drugs?|tablets?|tabs?|pills?|capsules?|doses?|dosage|dosing|injections?|"
    r"inject\w*|jabs?|syringe|insulin pen|pen needle)\b",
    # romanised Hindi / Bengali / Kannada (previous release)
    r"\b(?:dawa|dawai|davai|dawaai|davaai|dawaiyan|davaiyan|goli|goliyan|golee|khuraak|khurak|injection|"
    r"suee|oshudh|osudh|oshud|oushodh|aushadh|oshudher|aushadha|ausadha|maathre|maatre|matre|injekshan)\b",
    # es-ES
    r"\b(?:insulina\w*|metformina|glimepirida|gliclazida|sitagliptina|empagliflozina|dapagliflozina|semaglutida|"
    r"liraglutida|dulaglutida|tirzepatida|pioglitazona|acarbosa|estatinas?|atorvastatina|aspirina|medicamentos?|"
    r"medicinas?|f[aá]rmacos?|pastillas?|comprimidos?|c[aá]psulas?|dosis|inyecci[oó]n\w*|inyect\w*|jeringa\w*)\b",
    # fr-FR
    r"\b(?:insuline\w*|metformine|glim[eé]piride|s[eé]maglutide|liraglutide|tirz[eé]patide|statines?|atorvastatine|"
    r"aspirine|m[eé]dicaments?|comprim[eé]s?|cachets?|pilules?|g[eé]lules?|posologie|piq[uû]res? d'insuline|"
    r"seringue\w*|stylo [aà] insuline)\b",
    # de-DE
    r"\b(?:metformin|glimepirid|gliclazid|semaglutid|liraglutid|tirzepatid|statine?n?|atorvastatin|medikament\w*|"
    r"arznei\w*|tabletten?|pillen?|kapseln?|dosis|dosierung|insulinspritze\w*|injektion\w*|injizier\w*|spritze\w*)\b",
    # it-IT
    r"\b(?:metformina|glimepiride|semaglutide|liraglutide|statin[ae]|atorvastatina|aspirina|farmac[oi]|medicin[ae]|"
    r"medicinal[ei]|pastigli\w*|compress[ae]|pillol[ae]|capsul[ae]|dosi|dosaggio|iniezion[ei]|iniett\w*|siring\w*)\b",
    # ja-JP
    r"インスリン|インシュリン|メトホルミン|グリメピリド|ランタス|ノボラピッド|ヒューマログ|オゼンピック|薬|錠剤|服薬|投薬|"
    r"用量|投与量|注射|単位",
]
# A dose-like amount even without a drug word ("add 4 u", "10 IU", "500 mg" - but not "180 mg/dL").
DOSE_AMOUNT = (r"\d+(?:[.,]\d+)?\s*(?:(?:more|extra|additional|fewer|less|m[aá]s|menos|plus|de plus|mehr|weniger|"
               r"in pi[uù]|di pi[uù])\s+)?"
               r"(?:units?\b|u\b|iu\b|i\.u\.|mcg\b|µg|μg|mg\b(?!\s*/?\s*d\s*l)(?!\s*%)|"
               r"unidad(?:es)?\b|ui\b|unit[eé]s?\b|einheiten?\b|ie\b|unit[aà]|単位|ミリグラム)")
# Physiology terms that contain a drug word but are not medication content.
_PHYSIOLOGY = [r"\binsulin (?:sensitivity|resistance|response|action)\b",
               r"\b(?:sensibilidad|resistencia) a la insulina\b", r"\b(?:sensibilit[eé]|r[eé]sistance) [aà] l'insuline\b",
               r"\binsulin(?:sensitivit[aä]t|empfindlichkeit|resistenz)\b",
               r"\b(?:sensibilit[aà]|resistenza) all'insulina\b|\binsulino-?resistenza\b", r"インスリン(?:感受性|抵抗性)"]
# Reviewed referral phrasings (English) that may mention medicine without advising on it.
_SAFE_REFERRALS = [
    r"(?:please )?(?:ask|talk to|check with|consult|speak (?:to|with)) (?:your |a )?doctor (?:before|about) "
    r"(?:changing|stopping|starting|skipping|adjusting) (?:any|your) (?:medicines?|medications?|insulin)",
    r"(?:do not|don'?t|never) (?:change|stop|skip|start|adjust|alter) (?:any|your) (?:medicines?|medications?|"
    r"insulin|tablets?) without (?:asking |talking to )?(?:your |a )?doctor",
    r"i can'?t advise on (?:insulin|medicine)(?: or (?:insulin|medicine))? doses",
    r"i cannot advise on (?:insulin|medicine)(?: or (?:insulin|medicine))? doses",
]
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+|(?<=[。！？])\s*")


@lru_cache(maxsize=1)
def _safe_sentence_res() -> tuple[re.Pattern[str], ...]:
    """Every sentence of the fixed safety messages (all languages), as normalised regexes."""
    out: list[re.Pattern[str]] = []
    for msgs in MESSAGES.values():
        for txt in msgs.values():
            for sent in _SENT_SPLIT.split(txt):
                sent = sent.strip()
                if not sent:
                    continue
                pat = re.escape(_norm(sent)).replace(re.escape("{value}"), r"\d+(?:\.\d+)?")
                out.append(re.compile(pat))
    out += [_compiled(p) for p in _SAFE_REFERRALS + _PHYSIOLOGY]
    return tuple(out)


def medication_mentions(text: str) -> list[str]:
    """Medication terms / dose amounts left in ``text`` after removing reviewed safe sentences."""
    t = _norm(text)
    for rx in _safe_sentence_res():
        t = rx.sub(" ", t)
    hits = [m.group(0) for p in MED_TERMS for m in _compiled(p).finditer(t)]
    hits += [m.group(0) for m in _compiled(DOSE_AMOUNT).finditer(t)]
    return hits


def output_unsafe(text: str) -> bool:
    """Last line of defence on generated text: medication content only in reviewed wording."""
    return bool(medication_mentions(text))


# ----------------------------------------------------------------------------- reading policy
def reading_level(value: float) -> str:
    v = float(value)
    if v < VERY_LOW_BELOW:
        return "very_low"
    if v < LOW_BELOW:
        return "low"
    if v > VERY_HIGH_ABOVE:
        return "very_high"
    if v > HIGH_ABOVE:
        return "high"
    return "ok"


def assess_reading(value: float, symptoms_text: str | None = None, lang: str = DEFAULT_LANG) -> dict:
    """THE shared safety policy for a measured glucose value (mg/dL), used by manual entry, chat,
    chat confirmations and the replay reveal.

    Returns ``{level, emergency, title, message, actions, reason}`` localised to ``lang`` (unknown
    codes fall back to en-US). ``emergency``: a value below 54; below 70 with a low-sugar symptom;
    above 400 with vomiting / breathing / ketone / drowsiness words; or severe symptoms on their
    own in ``symptoms_text``."""
    lang = lang if lang in LANGS else DEFAULT_LANG
    v = float(value)
    level = reading_level(v)
    t = _norm(symptoms_text or "")
    low_sym = bool(_low_groups(t)) if t else False
    emergency, reason = False, None
    if level == "very_low":
        emergency, reason = True, "glucose_below_54"
    elif level == "low" and low_sym:
        emergency, reason = True, "low_with_symptoms"
    elif v > 400 and t and _any(HIGH_SYMPTOMS, t, normalised=True):
        emergency, reason = True, "high_with_symptoms"
    elif t and _any(EMERGENCY_PATTERNS, t, normalised=True):
        emergency, reason = True, "symptoms"
    vr = int(round(v))
    if emergency:
        msg_kind, title_kind, act_kind = "emergency", ("very_low" if level == "very_low" else "emergency"), "emergency"
    else:
        msg_kind = {"low": "hypo", "very_high": "hyper", "high": "high", "ok": "ok"}[level]
        title_kind, act_kind = level, level
    msg = message(msg_kind, lang, value=vr) if msg_kind in ("hypo", "hyper", "high") else message(msg_kind, lang)
    acts = READING_ACTIONS.get(act_kind, {})
    return {"level": level, "emergency": emergency, "title": READING_TITLES[title_kind][lang], "message": msg,
            "actions": list(acts.get(lang, acts.get(DEFAULT_LANG, []))),
            "reason": reason or (None if level == "ok" else f"{level}_reading"), "value": round(v, 1)}


def message(kind: str, lang: str, **kw: object) -> str:
    tpl = MESSAGES[kind].get(lang, MESSAGES[kind][DEFAULT_LANG])
    return tpl.format(**kw) if kw else tpl
