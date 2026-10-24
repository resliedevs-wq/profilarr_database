"""Emit non-sensitive regression cases for the real .NET regex engine."""
import json
from .test_policy import CASES, ROOT
from .evidence import annotate, pattern

cases = list(CASES)
for row in json.loads((ROOT / 'cjk/fixtures/doctor-x-e06.json').read_text(encoding='utf-8')):
    cases.append((row['title'], row['description'], row['expected']))
output = []
for title, description, expected in cases:
    for kind in ('any', 'simplified', 'traditional'):
        output.append({'pattern': pattern(kind), 'title': annotate(title, description),
                       'expected': bool(expected) if kind == 'any' else kind in expected})
print(json.dumps(output, ensure_ascii=True))
