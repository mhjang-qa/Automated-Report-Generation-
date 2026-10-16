from difflib import SequenceMatcher
from .query_normalizer import compact


def similarity(term, text):
    term, text = compact(term), compact(text)
    if not term or not text:
        return 0.0
    if term in text:
        return 1.0
    # Local windows keep long defect bodies from drowning short typo queries.
    size = len(term)
    if size < 3:
        return 0.0
    return max((SequenceMatcher(None, term, text[i:i+size], autojunk=False).ratio()
                for i in range(max(1, len(text)-size+1))), default=0.0)
