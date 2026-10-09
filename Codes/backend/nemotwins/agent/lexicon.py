"""Language-specific word lists and regexes for the rule router and the deterministic what-if parser.

Release languages (internal codes): en-US, es-ES, fr-FR, de-DE, it-IT, ja-JP.

Structure: every concept is written ONCE PER LANGUAGE in a ``*_BY_LANG`` dict (so a reviewer can read
one language at a time), and the orchestrator uses the combined alternation built by ``_any_of``
(the message language is not trusted for routing: people mix languages). Patterns are matched on
``normalise_digits(text.lower())`` unless noted.

Rules for writing patterns:
* Latin-script languages may use ``\\b`` (Python's ``\\w`` includes accented letters).
* Japanese has no word boundaries and kana/kanji count as ``\\w``: never use ``\\b`` in a ja pattern.
* Accents: add the unaccented spelling too where people commonly drop it (``que``/``qué``).
"""

from __future__ import annotations

LANGS = ("en-US", "es-ES", "fr-FR", "de-DE", "it-IT", "ja-JP")
DEFAULT_LANG = "en-US"


def _any_of(by_lang: dict[str, str]) -> str:
    """One capturing alternation ``((?:en)|(?:es)|...)`` over the languages that have a pattern."""
    return "(" + "|".join(f"(?:{p})" for p in by_lang.values() if p) + ")"


# ----------------------------------------------------------------------------- intents (rule router)
KW_BY_LANG: dict[str, dict[str, str]] = {
    "next_prick": {
        "en-US": (r"when would a (?:finger.?)?prick|prick (?:would )?tell you|reading (?:would )?(?:help|teach) you|"
                  r"when should i (?:check|test|prick)|best time to (?:check|test)|next (?:check|prick|test)"),
        "es-ES": (r"cu[aá]ndo (?:debo|deber[ií]a|tengo que|me toca|puedo) (?:volver a )?(?:medir|medirme|comprobar|"
                  r"hacer(?:me)? (?:la|una) (?:prueba|medici[oó]n))|pr[oó]xima (?:medici[oó]n|prueba|comprobaci[oó]n)|"
                  r"mejor momento para (?:medir|comprobar)"),
        "fr-FR": (r"quand (?:dois-je|devrais-je|faut-il|est-ce que je dois|je dois) (?:me )?(?:mesurer|piquer|contr[oô]ler|"
                  r"v[eé]rifier|tester|refaire)|prochaine (?:mesure|glyc[eé]mie|piq[uû]re|v[eé]rification)|"
                  r"meilleur moment pour (?:mesurer|contr[oô]ler|tester)"),
        "de-DE": (r"wann (?:soll|sollte|muss) ich\b.{0,40}?\b(?:messen|testen|pr[uü]fen|kontrollieren|stechen)|"
                  r"n[aä]chste (?:messung|kontrolle)|bester zeitpunkt (?:zum|f[uü]r die) (?:messen|messung)"),
        "it-IT": (r"quando (?:devo|dovrei|posso) (?:ri)?(?:misurar\w*|controllar\w*|fare (?:la|una) (?:misurazione|glicemia))|"
                  r"prossima (?:misurazione|glicemia|puntura)|momento migliore per (?:misurar|controllar)"),
        "ja-JP": r"いつ(?:測|はか|計|チェック|検査)|次(?:の|に)?(?:測定|血糖測定|チェック|検査)|測るべき|測ったらいい|測ればいい",
    },
    "log_reading": {
        "en-US": r"my (?:sugar|glucose|reading) (?:is|was)|reading (?:is|was)|i got \d+",
        "es-ES": (r"mi (?:glucosa|az[uú]car|glucemia|medici[oó]n|lectura) (?:es|est[aá]|era|ha sido|fue|ha dado|dio|de)\b|"
                  r"(?:glucosa|az[uú]car|glucemia) (?:de |en )?\d+|me (?:ha )?(?:salido|dado|dio|da) \d+"),
        "fr-FR": (r"ma (?:glyc[eé]mie|mesure) (?:est|[eé]tait|fait|[aà])\b|(?:glyc[eé]mie|sucre) (?:de |[aà] )?\d+|"
                  r"j'ai (?:eu|mesur[eé]) \d+"),
        "de-DE": (r"mein (?:blutzucker|zucker|zuckerwert|wert|messwert) (?:ist|war|liegt|lag|betr[aä]gt)\b|"
                  r"(?:blutzucker|zucker|zuckerwert) (?:von |bei )?\d+|ich habe \d+ gemessen"),
        "it-IT": r"la mia (?:glicemia|misurazione) (?:[eè]|era)\b|(?:glicemia|zucchero) (?:a |di )?\d+|ho misurato \d+",
        "ja-JP": r"血糖値?(?:は|が)?\s*\d+|測ったら\s*\d+|\d+\s*(?:でした|だった)",
    },
    "what_if": {
        "en-US": (r"what if|instead of|rather than|in place of|\bswap|\breplace|\bwalk|\bhalve|\bhalf\b|smaller|"
                  r"\beat (?:it )?(?:later|earlier)\b"),
        "es-ES": (r"qu[eé] pasa(?:r[ií]a)? si|\by si\b|en lugar de|en vez de|\bcambi(?:o|ar|ara|as)\b|sustitu\w*|"
                  r"\bcamin\w*|\bpase[oa]\w*|\bandar\b|la mitad|\bmitad\b|medi[oa] (?:raci[oó]n|porci[oó]n|plato)|"
                  r"m[aá]s tarde|m[aá]s temprano|diferencia"),
        "fr-FR": (r"\bet si\b|que se passe-t-il si|au lieu d|[aà] la place d|remplac\w*|rempla[cç]\w*|\bmarche\b|"
                  r"\bmarcher\b|\bpromen\w*|\bbalade\b|moiti[eé]|demi[- ]portion|plus tard|plus t[oô]t|diff[eé]rence"),
        "de-DE": (r"was w[aä]re,? wenn|was waere,? wenn|was passiert,? wenn|was ist,? wenn|\bstatt\b|anstatt|anstelle|"
                  r"ersetz\w*|\btausch\w*|spazier\w*|h[aä]lfte|halbe portion|halb so viel|sp[aä]ter essen|"
                  r"esse ich sp[aä]ter|fr[uü]her essen|unterschied"),
        "it-IT": (r"\be se\b|cosa succede(?:rebbe)? se|invece d\w*|al posto d\w*|sostitu\w*|cammin\w*|passeggi\w*|"
                  r"\bmet[aà]\b|mezza porzione|pi[uù] tardi|pi[uù] presto|differenza"),
        "ja-JP": (r"代わりに|かわりに|ではなく|じゃなくて|に(?:替え|変え|置き換え|かえ)|散歩|歩(?:い|く|け)|ウォーキング|"
                  r"半分|遅(?:く|め)に食べ|早(?:く|め)に食べ|違い|差は"),
    },
    "explain": {
        "en-US": r"\bwhy\b|reason",
        "es-ES": r"por qu[eé]|\bporqu[eé]\b|motivo|raz[oó]n|\bcausa\b",
        "fr-FR": r"pourquoi|\braison\b|\bcause\b",
        "de-DE": r"warum|wieso|weshalb|\bgrund\b|ursache",
        "it-IT": r"perch[eé]|\bmotivo\b|ragione|\bcausa\b",
        "ja-JP": r"なぜ|何故|どうして|なんで|理由|原因",
    },
    "outlook": {
        "en-US": r"90 days|three months|3 months|hba1c (?:will|going)|hba1c be|future",
        "es-ES": r"90 d[ií]as|tres meses|3 meses|futuro|a largo plazo",
        "fr-FR": r"90 jours|trois mois|3 mois|avenir|\bfutur\b|[aà] long terme",
        "de-DE": r"90 tage|drei monate|3 monate|zukunft|langfristig",
        "it-IT": r"90 giorni|tre mesi|3 mesi|futuro|lungo termine",
        "ja-JP": r"90日|3か月|3ヶ月|3カ月|三か月|将来|今後.{0,6}(?:見通し|予測)|長期",
    },
    "education": {
        "en-US": r"what is (?!my\b)|what does .* mean|meaning of|time in range",
        "es-ES": r"qu[eé] es (?!mi\b)|qu[eé] significa|significado de|tiempo en rango",
        "fr-FR": r"qu['’]est-ce que (?:c['’]est|le|la|l['’])|c['’]est quoi|que veut dire|que signifie|temps dans la cible",
        "de-DE": r"was ist (?!mein\b)(?!meine\b)|was bedeutet|was hei(?:ß|ss)t|bedeutung von|zeit im zielbereich",
        "it-IT": r"cos['’][eè]|cosa [eè]|che cos['’][eè]|cosa significa|che significa|cosa vuol dire|significato di|tempo nel range",
        "ja-JP": r"とは|って何|ってなに|どういう意味|意味は|目標範囲内時間",
    },
    "forecast": {
        "en-US": (r"if i (?:eat|have)|can i (?:eat|have)|should i eat|will .* (?:go|rise|spike)|\beat\b|\beating\b|\bhaving\b|"
                  r"\bdinner\b|\blunch\b|\bbreakfast\b"),
        "es-ES": (r"\bsi (?:me )?(?:como|tomo|ceno|desayuno|almuerzo)\b|puedo comer|deber[ií]a comer|\bcomer\b|\bcena\b|"
                  r"\bcenar\b|\balmuerzo\b|\bcomida\b|\bdesayuno\b|subir[aá]"),
        "fr-FR": (r"si je (?:mange|prends|d[iî]ne)|je peux manger|puis-je manger|dois-je manger|\bmanger\b|\bmange\b|"
                  r"\bd[iî]ner\b|\bd[eé]jeuner\b|\brepas\b|va monter|va augmenter"),
        "de-DE": (r"wenn ich .{0,40}(?:esse|trinke)|(?:darf|kann|soll) ich .{0,30}essen|\bessen\b|\besse\b|abendessen|"
                  r"mittagessen|fr[uü]hst[uü]ck|mahlzeit|\bsteigen\b|ansteigen"),
        "it-IT": (r"\bse mangio\b|\bse prendo\b|posso mangiare|dovrei mangiare|\bmangiare\b|\bmangio\b|\bcena\b|\bpranzo\b|"
                  r"colazione|\bpasto\b|salir[aà]|aumenter[aà]"),
        "ja-JP": r"食べ(?:たら|れば|ると|て|ます|る)|飲ん(?:だら|で)|夕食|夕飯|晩ご飯|晩ごはん|昼食|昼ご飯|朝食|朝ご飯|上が(?:る|り)|食事",
    },
    "state": {
        "en-US": r"how am i|my sugar now|right now|current",
        "es-ES": r"c[oó]mo estoy|ahora mismo|\bahora\b|actual",
        "fr-FR": r"comment je vais|o[uù] en suis-je|en ce moment|maintenant|actuel\w*",
        "de-DE": r"wie geht es mir|wie stehe ich|\bgerade\b|\bjetzt\b|aktuell\w*|momentan",
        "it-IT": r"come sto|adesso|in questo momento|\bora\b|attual\w*",
        "ja-JP": r"今|現在|いま",
    },
}
# Extra vocabulary added 2026-10-08 from the dev split of the multilingual suite (general words, not case text).
KW_EXTRA: dict[str, dict[str, str]] = {
    "forecast": {"en-US": r"\bforecast\b|\bprediction\b", "es-ES": r"pron[oó]stico|predicci[oó]n",
                 "fr-FR": r"pr[eé]vision|pr[eé]diction", "de-DE": r"prognose|vorhersage",
                 "it-IT": r"previsione|predizione", "ja-JP": r"予測|見通し"},
    "education": {"en-US": r"difference between", "es-ES": r"diferencia (?:hay )?entre|qu[eé] significa",
                  "fr-FR": r"diff[eé]rence entre|que signifie", "de-DE": r"unterschied zwischen|was bedeutet",
                  "it-IT": r"differenza (?:c'[eè] )?tra|cosa significa", "ja-JP": r"違い|どう違|とは何|の意味"},
}
for _intent, _by_lang in KW_EXTRA.items():
    for _lang, _pat in _by_lang.items():
        KW_BY_LANG[_intent][_lang] = f"(?:{KW_BY_LANG[_intent][_lang]})|(?:{_pat})"
KW: dict[str, str] = {intent: _any_of(by_lang) for intent, by_lang in KW_BY_LANG.items()}

# Off-topic requests. Only used when the message names no food and no glucose word, except
# recipes, which are off-topic even with a dish name ("how do I make biryani?").
OUT_OF_SCOPE_BY_LANG = {
    "en-US": (r"\bweather\b|\brain(?:ing)?\b tomorrow|\bcricket\b|\bipl\b|\bfootball\b|\bmatch score\b|\bscore\b|"
              r"\bwho won\b|\bjokes?\b|\bstory\b|\bpoem\b|\bsong\b|\bmovie\b|\bfilm\b|\bpolitic\w*|\belection\w*|"
              r"\bminister\b|\bnews\b|\bstock\w*|\bshare market\b|\bhoroscope\b|\btrain\b|\bticket\b|\bflight\b|"
              r"\bbook me\b|\bgst\b|\btax\w*\b|\bhomework\b|\bmaths?\b|\bcapital of\b|\btranslate\b"),
    "es-ES": (r"\btiempo (?:hace )?(?:ma[nñ]ana|hoy)\b|\bclima\b|\blluvia\b|llover[aá]|f[uú]tbol|\bpartido\b|"
              r"qui[eé]n gan[oó]|\bchistes?\b|\bcuento\b|\bpoema\b|canci[oó]n|pel[ií]cula|pol[ií]tic\w*|elecci\w*|"
              r"noticias|\bbolsa\b|\bacciones\b|hor[oó]scopo|\btren\b|\bbillete\b|\bvuelo\b|\bdeberes\b|"
              r"matem[aá]ticas|capital de|tradu(?:ce|cir|ceme)\b"),
    "fr-FR": (r"m[eé]t[eé]o|\bpluie\b|pleuvoir|pleuvra|\bfoot(?:ball)?\b|\bmatch\b|qui a gagn[eé]|\bblagues?\b|"
              r"\bhistoire\b|po[eè]me|chanson|\bfilm\b|politique|[eé]lections?\b|actualit[eé]s|\bbourse\b|horoscope|"
              r"\btrain\b|\bbillet\b|devoirs|math[eé]matiques|\bmaths\b|capitale d|tradui\w*"),
    "de-DE": (r"\bwetter\b|\bregen\b|fu(?:ß|ss)ball|wer hat gewonnen|\bwitze?\b|geschichte|gedicht|\blied\b|\bfilm\b|"
              r"politik|\bwahlen\b|nachrichten|\baktien?\b|b[oö]rse|horoskop|\bzug\b|fahrkarte|\bticket\b|\bflug\b|"
              r"hausaufgabe\w*|\bmathe\w*|hauptstadt|[uü]bersetz\w*"),
    "it-IT": (r"\bmeteo\b|\btempo (?:fa )?(?:domani|oggi)\b|pioggia|piover[aà]|\bcalcio\b|\bpartita\b|chi ha vinto|"
              r"barzellett\w*|\bstoria\b|poesia|canzone|\bfilm\b|politic\w*|elezion\w*|notizie|\bborsa\b|oroscopo|"
              r"\btreno\b|biglietto|\bvolo\b|\bcompiti\b|matematica|capitale d|tradu(?:ci|rre|zione)\b"),
    "ja-JP": (r"天気|雨|サッカー|野球|試合|スコア|誰が勝|冗談|ジョーク|物語|お話|詩|歌|映画|政治|選挙|ニュース|株価|株|"
              r"星占い|占い|電車|切符|チケット|飛行機|宿題|数学|首都|翻訳"),
}
OUT_OF_SCOPE = _any_of(OUT_OF_SCOPE_BY_LANG)

RECIPE_BY_LANG = {
    "en-US": r"\brecipe\w*|how (?:do|to|can) (?:i |you )?(?:make|cook|prepare)",
    "es-ES": r"\brecetas?\b|c[oó]mo (?:se )?(?:hace|prepara|cocina|hago|preparo|cocino)\b",
    "fr-FR": r"\brecettes?\b|comment (?:faire|pr[eé]parer|cuisiner|on (?:fait|pr[eé]pare))",
    "de-DE": r"\brezept\w*|wie (?:mache|koche|bereite|macht|kocht|bereitet) (?:ich|man)\b",
    "it-IT": r"\bricett\w*|come (?:si )?(?:fa|prepara|cucina|preparo|cucino)\b",
    "ja-JP": r"レシピ|作り方|どうやって作|調理法",
}
RECIPE = _any_of(RECIPE_BY_LANG)

IN_SCOPE_WORDS_BY_LANG = {
    "en-US": r"sugar|glucose|diabet\w*|hba1c|reading|peak|spike",
    "es-ES": r"glucosa|glucemia|az[uú]car|diab[eé]t\w*|medici[oó]n|\bpico\b",
    "fr-FR": r"glyc[eé]mie|sucre|diab[eè]t\w*|\bmesure\b|\bpic\b",
    "de-DE": r"zucker|glukose|diabet\w*|messwert|spitzenwert",
    "it-IT": r"glicemia|glucosio|zucchero|diabet\w*|misurazione|picco",
    "ja-JP": r"血糖|ブドウ糖|糖尿|ピーク|測定値",
}
IN_SCOPE_WORDS = _any_of(IN_SCOPE_WORDS_BY_LANG)

# "if ...": a value in a hypothetical question is not a reading to log.
HYPOTHETICAL_BY_LANG = {
    "en-US": r"\bif\b|what if",
    "es-ES": r"\bsi\b",            # "sí" (yes) keeps its accent
    "fr-FR": r"\bsi\b|\bs['’]il\b",
    "de-DE": r"\bwenn\b|\bfalls\b",
    "it-IT": r"\bse\b",
    "ja-JP": r"もし|としたら|だったら|場合",
}
HYPOTHETICAL = _any_of(HYPOTHETICAL_BY_LANG)

# ----------------------------------------------------------------------------- what-if parsing
LOW_RE_BY_LANG = {
    "en-US": r"\b(?:low|lows|hypo|hypoglyc\w*|below 70|under 70|go(?:ing)? down too)\b",
    "es-ES": (r"hipoglucemia|\bhipo\b|por debajo de 70|menos de 70|glucosa baja|az[uú]car baj\w*|\bbajar\w*|"
              r"\bbaje\b|\bbaj[oó]n\b|\bbajada\b"),
    "fr-FR": r"hypo\w*|en dessous de 70|sous 70|moins de 70|glyc[eé]mie basse|\bbaisser\w*|\bbaisse\b|\bchut\w*",
    "de-DE": r"unterzucker\w*|hypo\w*|unter 70|zu niedrig|\bniedrig\w*|\bsinken\b|\bsinkt\b|\bf[aä]llt\b|\bfallen\b",
    "it-IT": r"ipoglicemi\w*|\bipo\b|sotto (?:i )?70|meno di 70|glicemia bassa|\bscender\w*|\bscende\b|\bcala\w*|abbass\w*",
    "ja-JP": r"低血糖|70未満|70を下回|下が(?:る|り|って)|低く|低い",
}
LOW_RE = _any_of(LOW_RE_BY_LANG)

# Swap phrasings. BEFORE: the replaced food comes before the marker ("ご飯の代わりにパン",
# "Reis durch Roti ersetzen"). Matched on the ORIGINAL text, case-sensitive: write lower case.
SWAP_BEFORE_BY_LANG = {
    "de-DE": r"\bdurch\b(?=.{0,40}\bersetz)|\bgegen\b(?=.{0,40}\b(?:aus)?tausch)",
    "ja-JP": (r"の代わりに|のかわりに|の代わり|ではなく|じゃなくて|"
              r"を(?=[^を]{1,20}に(?:替え|変え|置き換え|かえ|切り替え|交換))"),
}
SWAP_BEFORE = _any_of(SWAP_BEFORE_BY_LANG)
# AFTER: the replaced food comes after the marker ("2 roti instead of rice", "pan en lugar de arroz").
SWAP_AFTER_BY_LANG = {
    "en-US": r"\b(?:instead of|rather than|in place of)\b",
    "es-ES": r"\b(?:en lugar de|en vez de)\b",
    "fr-FR": r"\bau lieu d(?:[eu]\b|['’])|\b[aà] la place d(?:[eu]\b|['’])",
    "de-DE": r"\b(?:statt|anstatt|anstelle von|anstelle|an stelle von)\b",
    "it-IT": r"\binvece d(?:i|el|ella|ello|ei|egli|elle)\b|\binvece d['’]|\bal posto d(?:i|el|ella|ello|ei|egli|elle)\b",
}
SWAP_AFTER = _any_of(SWAP_AFTER_BY_LANG)
# "swap/replace X for/with Y": exactly two groups, (X) and (Y). Verb first, so not used for Japanese
# (verb last: covered by SWAP_BEFORE).
SWAP_X_FOR_Y = (r"\b(?:swap|replace|switch|change|cambi(?:o|ar|as|a|ara)|sustitu\w*|reemplaz\w*|remplac\w*|rempla[cç]\w*|"
                r"[eé]chang\w*|ersetz\w*|tausch\w*|sostitu\w*|rimpiazz\w*)\b(.*?)"
                r"\b(?:for|with|to|por|par|durch|gegen|con|mit)\b(.*)")
HALF_RE_BY_LANG = {
    "en-US": r"\bhalf\b|\bhalve\b",
    "es-ES": r"\bla mitad\b|\bmitad\b|\bmedi[oa] (?:raci[oó]n|porci[oó]n|plato)",
    "fr-FR": r"\bmoiti[eé]\b|\bdemi[- ]portion\b|\bdemi\b",
    "de-DE": r"\bh[aä]lfte\b|\bhalbe\b|\bhalben\b|\bhalb\b|\bhalbier\w*",
    "it-IT": r"\bmet[aà]\b|\bmezza porzione\b|\bmezzo\b|\bmezza\b",
    "ja-JP": r"半分|半量|半人前",
}
HALF_RE = _any_of(HALF_RE_BY_LANG)
WALK_RE_BY_LANG = {
    "en-US": r"walk",
    "es-ES": r"\bcamin\w*|\bpase[oa]\w*|\bandar\b|\bandando\b",
    "fr-FR": r"\bmarche\b|\bmarcher\b|\bpromen\w*|\bbalade\b",
    "de-DE": r"spazier\w*|\blaufen\b|\blaufe\b|\bzu fu(?:ß|ss)\b",
    "it-IT": r"cammin\w*|passeggi\w*",
    "ja-JP": r"散歩|歩(?:い|く|け|き)|ウォーキング",
}
WALK_RE = _any_of(WALK_RE_BY_LANG)
# Minutes: "15 min", "15-minute", "15 minutos", "15 Minuten", "15 minuti", "15分".
MIN_RE = r"(\d+)\s*(?:-?\s*min|分)"
LATER_RE_BY_LANG = {
    "en-US": r"\beat (?:it )?later\b|\blater\b",
    "es-ES": r"m[aá]s tarde",
    "fr-FR": r"plus tard",
    "de-DE": r"sp[aä]ter",
    "it-IT": r"pi[uù] tardi",
    "ja-JP": r"遅く|遅め|後で食べ|あとで食べ",
}
LATER_RE = _any_of(LATER_RE_BY_LANG)
EARLIER_RE_BY_LANG = {
    "en-US": r"\beat (?:it )?earlier\b|\bearlier\b",
    "es-ES": r"m[aá]s temprano|m[aá]s pronto",
    "fr-FR": r"plus t[oô]t",
    "de-DE": r"fr[uü]her",
    "it-IT": r"pi[uù] presto|in anticipo",
    "ja-JP": r"早く食べ|早めに|早め",
}
EARLIER_RE = _any_of(EARLIER_RE_BY_LANG)

# ----------------------------------------------------------------------------- reply language
AND_WORD = {"en-US": "and", "es-ES": "y", "fr-FR": "et", "de-DE": "und", "it-IT": "e", "ja-JP": "と"}
# Reply-language names for the planner prompt ("Reply in {lang_name} only").
LANG_NAME = {
    "en-US": "plain international English",
    "es-ES": "Spanish (Spain), polite 'usted' form",
    "fr-FR": "French (France), polite 'vous' form",
    "de-DE": "German, polite 'Sie' form",
    "it-IT": "Italian, polite 'Lei' form",
    "ja-JP": "Japanese, polite です/ます form",
}
TERMINAL = {"en-US": ".", "es-ES": ".", "fr-FR": ".", "de-DE": ".", "it-IT": ".", "ja-JP": "。"}
