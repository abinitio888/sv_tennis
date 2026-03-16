"""
Classifies raw event names into normalized categories.
"""
import re

# Ordered list of (pattern, category) — first match wins.
# No trailing word-boundary on patterns that can be followed by extra word chars.
_RULES = [
    # Juniors
    (r"(?:^|\s|-)(?:PS\s*1[02468]|POJK|FLICKA)", "juniors"),
    (r"\bJUNIOR", "juniors"),                          # JUNIOR, JUNIORSINGEL, etc.
    (r"\bU\d{1,2}\b", "juniors"),
    # Senior/Veteran
    (r"\bVETERAN\b|\bVET\b", "senior_plus"),
    (r"[456789][05]\s*\+", "senior_plus"),              # 45+, 50+, 55+ ...
    (r"[456789][05]\s*PLUS", "senior_plus"),
    # Mixed doubles
    (r"\bMX\b|\bMIXED\b|\bBLANDDUBB?EL\b|\bBLAND\s*DUBB?EL\b|\bMIX\b", "mixed_doubles"),
    # Womens doubles
    (r"\bDD\b|\bDAMDUBBEL\b|\bDAM\s*DUBBEL\b|\bWD\b", "womens_doubles"),
    # Mens doubles
    (r"\bHD\b|\bHERRDUBBEL\b|\bHERR\s*DUBBEL\b|\bMD\b", "mens_doubles"),
    # Womens singles
    (r"\bDS\b|\bDAMSINGEL\b|\bDAM\s*SINGEL\b|\bWS\b", "womens_singles"),
    # Mens singles
    (r"\bHS\b|\bHERRSINGEL\b|\bHERR\s*SINGEL\b|\bMS\b", "mens_singles"),
    # Generic doubles fallback
    (r"\bDUBBEL\b|\bDOUBLES?\b", "mens_doubles"),
    # Generic singles fallback
    (r"\bSINGEL\b|\bSINGLES?\b", "mens_singles"),
]

_COMPILED = [(re.compile(pat, re.IGNORECASE), cat) for pat, cat in _RULES]

_DOUBLES_CATS = {"mens_doubles", "womens_doubles", "mixed_doubles"}


def classify_event(event_name: str) -> str:
    """Return normalized event category for a raw event name string."""
    if not event_name:
        return "other"
    for pattern, category in _COMPILED:
        if pattern.search(event_name):
            return category
    return "other"


def is_doubles(event_category: str) -> bool:
    return event_category in _DOUBLES_CATS
