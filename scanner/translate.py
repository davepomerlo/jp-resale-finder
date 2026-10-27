"""Japanese → English title translation with a local cache.

Uses DeepL API Free (500,000 characters/month free) when DEEPL_API_KEY is set.
Without a key, titles stay in Japanese and the app offers a Google Translate link.
"""
import json
import os
from pathlib import Path

import requests

CACHE = Path(__file__).parent / "cache" / "translations.json"


class Translator:
    def __init__(self, mock=False):
        self.key = os.environ.get("DEEPL_API_KEY", "")
        self.mock = mock
        self.cache = {}
        if mock:
            sample = Path(__file__).parent / "fixtures" / "translations_sample.json"
            self.cache = json.loads(sample.read_text(encoding="utf-8")) if sample.exists() else {}
        elif CACHE.exists():
            try:
                self.cache = json.loads(CACHE.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                self.cache = {}
        self.enabled = bool(self.key) or mock

    def translate_many(self, texts):
        todo = [t for t in dict.fromkeys(texts) if t and t not in self.cache]
        if todo and self.key and not self.mock:
            host = "api-free.deepl.com" if self.key.endswith(":fx") else "api.deepl.com"
            for start in range(0, len(todo), 40):
                batch = todo[start:start + 40]
                try:
                    r = requests.post(
                        f"https://{host}/v2/translate",
                        headers={"Authorization": f"DeepL-Auth-Key {self.key}"},
                        data=[("text", t) for t in batch] + [("source_lang", "JA"), ("target_lang", "EN-US")],
                        timeout=30,
                    )
                    r.raise_for_status()
                    for src, tr in zip(batch, r.json()["translations"]):
                        self.cache[src] = tr["text"]
                except Exception as e:  # translation is optional — never fail the scan
                    print(f"[translate] skipped: {e}")
                    break
        return {t: self.cache.get(t) for t in texts}

    def save(self):
        if self.mock:
            return
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        # keep the cache from growing forever
        items = list(self.cache.items())[-5000:]
        CACHE.write_text(json.dumps(dict(items), ensure_ascii=False, indent=0), encoding="utf-8")
