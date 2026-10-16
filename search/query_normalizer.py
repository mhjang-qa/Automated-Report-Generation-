import re
import unicodedata


def normalize(text):
    return re.sub(r'[^a-z0-9가-힣]+', ' ', unicodedata.normalize('NFKC', str(text)).lower()).strip()


def compact(text):
    return normalize(text).replace(' ', '')


def grams(text):
    value = compact(text)
    return {value[i:i+2] for i in range(len(value)-1)} | ({ch for ch in value if '가' <= ch <= '힣'} if len(value) == 1 else set())
