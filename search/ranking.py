from .models import FIELD_WEIGHTS
from .query_normalizer import compact
from .fuzzy_matcher import similarity

LABELS = {'title': '제목', 'screen': '화면/기능', 'actual': '실제 결과', 'steps': '재현절차',
          'expected': '예상 결과', 'body': '본문', 'comments': '댓글'}


def rank(document, query, keywords, synonyms, semantic):
    fields = {name: compact(synonyms.canonicalize(document.get(name, ''))) for name in FIELD_WEIGHTS}
    raw_query = compact(query)
    cq = compact(synonyms.canonicalize(query))
    exact = raw_query == compact(document['title'])
    partial = bool(raw_query and raw_query in compact(document['title']))
    matches, reasons, evidence = [], [], {}
    fuzzy_values = []
    non_os = [k for k in keywords if k not in {'aos', 'ios', '공통'}]
    for word in non_os:
        locations = [name for name, text in fields.items() if compact(word) in text]
        if locations:
            matches.append(word)
            evidence[word] = max(FIELD_WEIGHTS[name] for name in locations)
            name = locations[0]
            alias_note = ' (유사 표현 일치)' if compact(word) not in compact(document.get(name, '')) else ''
            reasons.append(f'{LABELS[name]}: {word}{alias_note}')
            fuzzy_values.append(1)
        else:
            # Fuzzy only on high-value fields, bounded to avoid quadratic body scans.
            value = max(similarity(word, fields[name][:1000]) for name in ('title', 'screen', 'actual'))
            fuzzy_values.append(value if value >= .66 else 0)
            if value >= .66:
                reasons.append(f'유사 표현/오타: {word}')
    denominator = max(1, len(non_os))
    coverage = len(matches) / denominator
    field_score = sum(evidence.values()) / denominator
    fuzzy = sum(fuzzy_values) / denominator
    platforms = [os for os in ('aos', 'ios') if os in keywords]
    doc_os = compact(synonyms.canonicalize(document.get('platform', '') + ' ' + document['title']))
    os_match = bool(platforms and (any(os in doc_os for os in platforms) or '공통' in doc_os))
    if os_match:
        reasons.append('OS 일치: ' + ', '.join(platforms))
    exact_score = 1.0 if exact else (.85 if partial else 0.0)
    score = 40*coverage + 20*field_score + 15*fuzzy + 20*semantic + 5*os_match
    if exact:
        score = 100
        reasons.insert(0, '제목 완전 일치')
    elif partial:
        score = max(score, 85 + 10*coverage + 5*semantic)
        reasons.insert(0, '제목 부분 일치')
    if platforms and not os_match and doc_os and ('aos' in doc_os or 'ios' in doc_os):
        score *= .8
    relevant = exact or partial or bool(matches) or (fuzzy >= .66 and bool(non_os))
    if not non_os and os_match:
        relevant, score = True, max(score, 40)
    return {
        'score': round(min(100, max(0, score)), 1), 'matched_keywords': matches,
        'reasons': list(dict.fromkeys(reasons)), '_relevant': relevant,
        '_debug': {'exact_score': exact_score, 'keyword_score': coverage,
                   'fuzzy_score': fuzzy, 'semantic_score': semantic,
                   'field_score': field_score, 'field_weights': FIELD_WEIGHTS,
                   'os_match': os_match, 'final_score': round(min(100, max(0, score)), 1)}
    }
