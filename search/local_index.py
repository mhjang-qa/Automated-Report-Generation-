"""Transactional SQLite documents + bigram inverted index (Korean whitespace tolerant)."""
import json
import sqlite3
from pathlib import Path
from .models import FIELD_WEIGHTS
from .query_normalizer import compact, grams


class LocalIndex:
    def __init__(self, path, synonyms):
        self.path, self.synonyms = Path(path), synonyms
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS documents (id TEXT PRIMARY KEY, data TEXT, text TEXT, title TEXT);
                CREATE TABLE IF NOT EXISTS postings (gram TEXT, id TEXT, PRIMARY KEY(gram,id));
                CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT);
            ''')

    def connect(self):
        return sqlite3.connect(str(self.path), timeout=30)

    def snapshot(self):
        with self.connect() as db:
            return {key: json.loads(value) for key, value in db.execute('SELECT key,value FROM metadata')}

    def all_documents(self):
        with self.connect() as db:
            return {key: json.loads(data) for key, data in db.execute('SELECT id,data FROM documents')}

    def replace(self, documents, metadata):
        # Readers keep the last complete snapshot until this single transaction commits.
        with self.connect() as db:
            db.execute('DELETE FROM documents')
            db.execute('DELETE FROM postings')
            db.execute('DELETE FROM metadata')
            for doc in documents:
                text = compact(self.synonyms.canonicalize(' '.join(str(doc.get(k, '')) for k in [*FIELD_WEIGHTS, 'platform'])))
                db.execute('INSERT OR REPLACE INTO documents VALUES (?,?,?,?)',
                           (doc['id'], json.dumps(doc, ensure_ascii=False), text, compact(doc['title'])))
                db.executemany('INSERT OR IGNORE INTO postings VALUES (?,?)', ((g, doc['id']) for g in (grams(text) | {ch for ch in text if '가' <= ch <= '힣'})))
            db.executemany('INSERT INTO metadata VALUES (?,?)', ((k, json.dumps(v, ensure_ascii=False)) for k,v in metadata.items()))

    def candidates(self, query, keywords, limit=500):
        query_grams = sorted(grams(self.synonyms.canonicalize(query)) | {g for k in keywords for g in grams(k)})[:512]
        with self.connect() as db:
            if not query_grams:
                return []
            marks = ','.join('?' for _ in query_grams)
            rows = db.execute(f'''SELECT d.data FROM postings p JOIN documents d ON d.id=p.id
                WHERE p.gram IN ({marks}) GROUP BY p.id
                ORDER BY (d.title=?) DESC, (instr(d.title,?)>0) DESC, COUNT(*) DESC, p.id LIMIT ?''',
                (*query_grams, compact(query), compact(query), limit)).fetchall()
            return [json.loads(row[0]) for row in rows]
