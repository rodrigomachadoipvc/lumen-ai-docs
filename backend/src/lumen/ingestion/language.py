"""Pick the PostgreSQL text-search configuration for a document."""

import re

# Common words that exist in only one of the two languages. Words spelled the same in both
# ("a", "do", "as", "no", "me") are left out, so short questions are not misread.
_STOPWORDS: dict[str, frozenset[str]] = {
    "portuguese": frozenset(
        "o os da dos das em na nos nas um uma que não para com por se ao à é são foi está "
        "mais como mas ou seu sua pelo pela entre também qual quais quanto quantos quantas "
        "quem onde quando porque posso pode tenho há eu meu minha".split()
    ),
    "english": frozenset(
        "the of and to in is are was were for on with by that this it be at from or an "
        "not which have has but their how what who when where why does did you your my "
        "can many much get i we they there".split()
    ),
}

SEARCH_LANGUAGES: tuple[str, ...] = tuple(_STOPWORDS)
FALLBACK_LANGUAGE = "simple"
_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)


def detect_language(text: str, sample_chars: int = 20_000) -> str:
    words = [w.lower() for w in _WORD.findall(text[:sample_chars])]
    if not words:
        return FALLBACK_LANGUAGE
    scores = {lang: sum(w in stop for w in words) for lang, stop in _STOPWORDS.items()}
    best, score = max(scores.items(), key=lambda item: item[1])
    # Require some evidence; otherwise index without stemming.
    return best if score / len(words) >= 0.05 else FALLBACK_LANGUAGE
