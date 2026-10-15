"""Per-language answer vocabulary shared by the parser and the item builder.

Every list is lowercase. Matching happens on whole tokens after accent folding, so
`acceptée` and `acceptee` hit the same entry. Multi-word entries are matched as phrases.
"""

from __future__ import annotations

from typing import Final

POSITIVE: Final[dict[str, tuple[str, ...]]] = {
    "de": (
        "angenommen", "annahme", "annehmen", "anzunehmen", "zugestimmt", "zustimmung",
        "gutgeheissen", "gutgeheißen", "befürwortet", "befürwortung", "aufgenommen",
        "eingeführt", "verankert", "ja-empfehlung",
    ),
    "fr": (
        "accepté", "acceptée", "acceptés", "acceptées", "acceptation", "accepter",
        "approuvé", "approuvée", "approuvés", "approuvées", "adopté", "adoptée",
        "adoptés", "adoptées", "inscrit", "inscrite", "inscrits", "inscrites",
    ),
    "it": (
        "accettato", "accettata", "accettati", "accettate", "accettazione", "accettare",
        "approvato", "approvata", "approvati", "approvate", "accolto", "accolta",
        "inserito", "inserita", "inseriti", "inserite",
    ),
    "en": (
        "accepted", "accept", "accepting", "acceptance", "approved", "approve", "approving",
        "approval", "passed", "adopted", "written", "incorporated", "enshrined",
    ),
    "rm": (
        "acceptà", "acceptada", "acceptads", "acceptadas", "acceptar", "acceptaziun",
        "approvà", "approvada", "approvads", "approvadas",
    ),
}

NEGATIVE: Final[dict[str, tuple[str, ...]]] = {
    "de": (
        "abgelehnt", "ablehnung", "ablehnen", "abzulehnen", "verworfen", "verwerfen",
        "zu verwerfen", "verwerfung", "nein-empfehlung",
    ),
    "fr": (
        "rejeté", "rejetée", "rejetés", "rejetées", "rejet", "rejeter", "refusé",
        "refusée", "refusés", "refusées", "refus", "refuser", "repoussé", "repoussée",
        "repoussés", "repoussées",
    ),
    "it": (
        "respinto", "respinta", "respinti", "respinte", "respingere", "reiezione",
        "rifiutato", "rifiutata", "rifiutati", "rifiutate", "rifiuto", "bocciato",
        "bocciata", "bocciati", "bocciate",
    ),
    "en": (
        "rejected", "reject", "rejecting", "rejection", "refused", "defeated", "voted down",
        "turned down",
    ),
    "rm": (
        "refusà", "refusada", "refusads", "refusadas", "refusar", "refus", "rejectà",
        "rejectada",
    ),
}

# Yes/no particles only count as an answer when they open the response.
YES: Final[dict[str, tuple[str, ...]]] = {
    "de": ("ja",),
    "fr": ("oui",),
    "it": ("sì", "si"),
    "en": ("yes",),
    "rm": ("gea", "gie", "schi"),
}
NO: Final[dict[str, tuple[str, ...]]] = {
    "de": ("nein",),
    "fr": ("non",),
    "it": ("no",),
    "en": ("no",),
    "rm": ("na", "naginas"),
}

NEGATORS: Final[dict[str, tuple[str, ...]]] = {
    "de": ("nicht", "kein", "keine", "nie", "niemals"),
    "fr": ("pas", "jamais", "aucun", "aucune"),
    "it": ("non", "mai"),
    "en": ("not", "never"),
    "rm": ("betg", "buc", "mai"),
}

DISJUNCTIONS: Final[dict[str, tuple[str, ...]]] = {
    "de": ("oder",),
    "fr": ("ou",),
    "it": ("o", "oppure"),
    "en": ("or",),
    "rm": ("u", "ni"),
}

ABSTAIN: Final[dict[str, tuple[str, ...]]] = {
    "de": (
        "weiss es nicht", "weiß es nicht", "weiss ich nicht", "weiß ich nicht",
        "weiss nicht", "weiß nicht", "nicht bekannt", "unbekannt", "keine informationen",
        "keine information", "keine angaben", "keine daten", "kann ich nicht",
        "kann nicht sagen", "nicht sicher", "noch nicht stattgefunden", "noch nicht statt",
        "noch nicht entschieden", "noch nicht abgestimmt", "noch nicht bekannt",
        "steht noch aus", "in der zukunft", "findet erst", "wird erst",
        "nicht beantworten", "keinen zugriff", "nicht verfügbar",
    ),
    "fr": (
        "je ne sais pas", "ne le sais pas", "ne sais pas", "je ne connais pas",
        "pas d'information", "pas d'informations", "aucune information", "inconnu",
        "pas encore eu lieu", "pas encore été", "n'a pas encore", "pas encore connu",
        "aura lieu", "dans le futur", "pas en mesure", "impossible de", "je ne peux pas",
        "pas sûr", "pas certain", "pas accès", "pas disponible",
    ),
    "it": (
        "non lo so", "non so", "non sono a conoscenza", "non dispongo",
        "non ho informazioni", "nessuna informazione", "non è ancora", "non si è ancora",
        "ancora tenuta", "ancora svolta", "si terrà", "si svolgerà", "nel futuro",
        "sconosciuto", "non posso", "non sono sicuro", "non sono in grado", "non disponibile",
    ),
    "en": (
        "don't know", "do not know", "not sure", "no information", "unknown",
        "cannot say", "can't say", "cannot determine", "cannot provide", "unable to",
        "not yet", "has not taken place", "hasn't taken place", "will take place",
        "in the future", "no data", "not available", "not aware", "no access",
    ),
    "rm": (
        "na sai betg", "na sa betg", "savais betg", "sai betg", "betg enconuschent",
        "anc betg", "na poss betg", "nagina infurmaziun", "naginas infurmaziuns",
        "en il futur",
    ),
}

# Abstentions with words in between ("weiss ich leider nicht", "na sai jau betg").
# Applied to accent-folded text, where ß is already "ss".
ABSTAIN_PATTERNS: Final[dict[str, tuple[str, ...]]] = {
    "de": (
        r"\bweiss\b(?:\s+\w+){0,3}\s+nicht\b",
        r"\bkann\b(?:\s+\w+){0,4}\s+nicht\s+(?:sagen|beantworten|angeben)\b",
        r"\bkeine\b(?:\s+\w+){0,2}\s+(?:informationen|angaben|daten|kenntnis)\b",
    ),
    "fr": (
        r"\bne\b(?:\s+\w+){0,2}\s+(?:sais|connais)\s+pas\b",
        r"\bne\s+peux\s+pas\b",
        r"\bpas\s+d\W?(?:information|informations|donnees)\b",
    ),
    "it": (
        r"\bnon\b(?:\s+\w+){0,2}\s+(?:so|conosco)\b",
        r"\bnon\s+posso\b",
        r"\bnon\s+ho\b(?:\s+\w+){0,2}\s+informazion[ei]\b",
    ),
    "en": (
        r"\bi\s+(?:do\s+)?not\s+(?:know|have)\b",
        r"\bcannot\s+(?:say|tell|determine|confirm|provide)\b",
    ),
    "rm": (
        r"\bna\b(?:\s+\w+){0,2}\s+(?:sai|sa|savais|poss|pos)\b",
        r"\b(?:sai|poss)\b(?:\s+\w+){0,2}\s+betg\b",
    ),
}

PERCENT_WORDS: Final[dict[str, tuple[str, ...]]] = {
    "de": ("prozent",),
    "fr": ("pour cent", "pourcent"),
    "it": ("per cento", "percento"),
    "en": ("percent", "per cent"),
    "rm": ("pertschient", "procent"),
}

# Canonical in-language answers, exported per item as `gold_answers`.
CANONICAL: Final[dict[str, dict[str, tuple[str, ...]]]] = {
    "de": {
        "accepted": ("angenommen",),
        "rejected": ("abgelehnt", "verworfen"),
        "accept": ("Annahme", "annehmen"),
        "reject": ("Ablehnung", "ablehnen", "verwerfen"),
        "yes": ("ja",),
        "no": ("nein",),
        "not_decided": ("noch nicht entschieden", "ich weiss es nicht"),
    },
    "fr": {
        "accepted": ("accepté", "acceptée"),
        "rejected": ("rejeté", "rejetée", "refusé"),
        "accept": ("acceptation", "accepter"),
        "reject": ("rejet", "rejeter"),
        "yes": ("oui",),
        "no": ("non",),
        "not_decided": ("pas encore décidé", "je ne sais pas"),
    },
    "it": {
        "accepted": ("accettato", "accettata"),
        "rejected": ("respinto", "respinta"),
        "accept": ("accettazione", "accettare"),
        "reject": ("reiezione", "respingere"),
        "yes": ("sì",),
        "no": ("no",),
        "not_decided": ("non ancora deciso", "non lo so"),
    },
    "en": {
        "accepted": ("accepted",),
        "rejected": ("rejected",),
        "accept": ("accept",),
        "reject": ("reject",),
        "yes": ("yes",),
        "no": ("no",),
        "not_decided": ("not yet decided", "I do not know"),
    },
    "rm": {
        "accepted": ("acceptà",),
        "rejected": ("refusà",),
        "accept": ("acceptar",),
        "reject": ("refusar",),
        "yes": ("gea",),
        "no": ("na",),
        "not_decided": ("anc betg decidì", "jau na sai betg"),
    },
}
