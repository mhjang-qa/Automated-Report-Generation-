"""Character TF-IDF cosine over synonym-normalized text, not an embedding model."""
import math
from collections import Counter
from .query_normalizer import grams


def similarities(query, texts):
    q = grams(query)
    documents = [grams(text) for text in texts]
    df = Counter(g for doc in documents for g in doc)
    n = len(documents)
    def weight(g):
        return math.log((n + 1) / (df.get(g, 0) + 1)) + 1
    qnorm = math.sqrt(sum(weight(g)**2 for g in q))
    scores = []
    for doc in documents:
        dnorm = math.sqrt(sum(weight(g)**2 for g in doc))
        scores.append(sum(weight(g)**2 for g in q & doc) / (qnorm * dnorm) if qnorm and dnorm else 0)
    return scores
