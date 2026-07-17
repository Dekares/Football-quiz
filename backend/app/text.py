"""İsim normalizasyonu — arama ve karşılaştırma için tek kaynak.

Hem çalışma anı API'si hem de data/pipeline/publish.py aynı kuralı kullanır;
böylece DB'deki search_name/search_alias ile gelen sorgu birebir eşleşir.
"""
from __future__ import annotations

import re
import unicodedata

# Aksanlı/özel harfler için NFKD'nin yakalamadığı eşlemeler.
_REPLACEMENTS = {
    "ı": "i", "İ": "i", "ø": "o", "Ø": "o", "ł": "l", "Ł": "l",
    "đ": "d", "Đ": "d", "ß": "ss", "æ": "ae", "Æ": "ae",
    "œ": "oe", "Œ": "oe", "þ": "th", "Þ": "th",
}
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize_text(s: str | None) -> str:
    """'Özil' -> 'ozil', "N'Golo Kanté" -> 'ngolo kante', 'Müller' -> 'muller'."""
    if not s:
        return ""
    for src, dst in _REPLACEMENTS.items():
        s = s.replace(src, dst)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return " ".join(_NON_ALNUM.sub(" ", s).split())
