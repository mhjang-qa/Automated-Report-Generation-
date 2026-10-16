import json
import re
from pathlib import Path
from .query_normalizer import normalize, compact


class SynonymManager:
    def __init__(self, path=None):
        path = path or Path(__file__).resolve().parents[1] / 'config/search_synonyms.json'
        self.groups = json.loads(Path(path).read_text(encoding='utf-8'))
        self.aliases = sorted({(compact(alias), key) for key, aliases in self.groups.items()
                               for alias in [key, *aliases]}, key=lambda p: -len(p[0]))
        # English abbreviations need boundaries: BS must not match 'subscribe'.
        self.pattern = re.compile('|'.join(
            (r'(?<![a-z0-9])' + r'\s*'.join(re.escape(ch) for ch in alias) + r'(?![a-z0-9])')
            if alias.isascii() else r'\s*'.join(re.escape(ch) for ch in alias)
            for alias, _ in self.aliases))
        self.lookup = dict(self.aliases)

    def canonicalize(self, text):
        value = normalize(text)
        return self.pattern.sub(lambda m: ' ' + self.lookup[compact(m.group())] + ' ', value).strip()

    def expanded(self, keywords):
        return {word: self.groups.get(word, [word]) for word in keywords}
