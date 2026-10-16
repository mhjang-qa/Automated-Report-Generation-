import re
from .query_normalizer import normalize, compact

STOP = {'에서', '에서의', '으로', '하면', '현상', '결함', '관련', '진행', '이후', '완료', '후', '시', '안', '화면', '메뉴', '것', '합니다'}
SUFFIX = re.compile(r'(에서는|에서|으로|하고|하면|하면은|관련|결함|현상|으로의|에|을|를|이|가|은|는|도)$')


def extract(query, synonyms):
    text = synonyms.canonicalize(query)
    terms = []
    for token in text.split():
        if token not in synonyms.groups:
            token = SUFFIX.sub('', token)
        if (len(token) >= 2 or token in synonyms.groups) and token not in STOP:
            terms.append(token)
    return list(dict.fromkeys(terms))[:32]
