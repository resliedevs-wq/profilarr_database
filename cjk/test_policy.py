"""Offline regression suite: evidence, database replay, and HTTP behavior."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import sqlite3
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

from .build_policy import ROOT, OUTPUT, PROFILE, BASE, MISSING, generate
from .evidence import annotate, classify, pattern
from .feed_adapter import make_handler, transform

CASES = [
    ('Show.S01E06.1080p.WEB-DL-GROUP', '', []),
    ('电影.2026.2160p.国语.双语-GROUP', '', []),
    ('Show.S01E06.1080p.Mandarin.DUAL.MULTI-GROUP', '', []),
    ('Show.S01E06.CHINESE-GROUP', '', []),
    ('Show.S01E06.CHS-GROUP', '', ['simplified']),
    ('Show.S01E06.CHT-GROUP', '', ['traditional']),
    ('Show.S01E06.CHS.CHT-GROUP', '', ['simplified', 'traditional']),
    ('Show.S01E06-GROUP', '[韩语] [简繁英字幕]', ['simplified', 'traditional']),
    ('Show.S01E06-GROUP', '[简英字幕]', ['simplified']),
    ('Show.S01E06-GROUP', '[繁英字幕]', ['traditional']),
    ('Show.S01E06-GROUP', '内封中文字幕', ['unspecified']),
    ('Show.S01E06-GROUP', '內嵌中字', ['unspecified']),
    ('Show.S01E06-GROUP', '<b>简体中文字幕</b>', ['simplified']),
    ('Show.S01E06-GROUP', '&lt;b&gt;繁體字幕&lt;/b&gt;', ['traditional']),
    ('Show.S01E06-GROUP', 'Chinese subtitles', ['unspecified']),
    ('Show.S01E06-GROUP', 'Simplified Chinese subtitles', ['simplified']),
    ('Show.S01E06-GROUP', 'Traditional Chinese subs', ['traditional']),
    ('Show.S01E06-GROUP', 'zh-Hans subtitles', ['simplified']),
    ('Show.S01E06-GROUP', 'zh-Hant subs', ['traditional']),
    ('Show.S01E06.CHSTeam-GROUP', '', []),
    ('Show.S01E06-GROUP', '<script>CHS</script>', []),
    ('Show.S01E06-GROUP', '<img alt="CHS" src="CHS.png">', []),
    ('Show.S01E06.CHS-GROUP', '无字幕', []),
    ('Show.S01E06.CHS-GROUP', '无中文字幕', []),
    ('Show.S01E06.CHT-GROUP', '無中文字幕', []),
    ('Show.S01E06.CHS-GROUP', '中文字幕：无', []),
    ('Show.S01E06.CHS-GROUP', '没有中文字幕', []),
    ('Show.S01E06.CHS-GROUP', 'Chinese subtitles: none', []),
    ('Show.S01E06.CHS-GROUP', 'No Chinese subtitles', []),
    ('Show.S01E06.CHS-GROUP', 'without subtitles', []),
    ('Show.S01E06.CHS-GROUP', 'No English subtitles', ['simplified']),
    ('Show.S01E06.CJKSubS.CJKSubNO-GROUP', '', []),
    ('Show.S01E06-GROUP', 'MULTI / Korean / 中文字幕待发布', []),
]

def replay(local=True):
    db = sqlite3.connect(':memory:')
    db.execute('PRAGMA foreign_keys=ON')
    for folder in (ROOT / 'vendor/schema-1.1.0/ops', ROOT / 'ops'):
        for file in sorted(folder.glob('*.sql'), key=lambda f: int(f.name.split('.')[0])):
            if not local and file == OUTPUT:
                continue
            try:
                # Match Profilarr 2.3.1: foreign keys enabled, execute each op.
                db.executescript(file.read_text(encoding='utf-8-sig'))
            except Exception as exc:
                raise RuntimeError(file.name) from exc
    return db

class EvidenceTests(unittest.TestCase):
    def test_claims(self):
        for title, desc, expected in CASES:
            with self.subTest(title=title, description=desc):
                self.assertEqual(classify(title, desc), set(expected))

    def test_annotation_and_arr_regex_agree(self):
        for title, desc, expected in CASES:
            with self.subTest(title=title, description=desc):
                output = annotate(title, desc)
                self.assertEqual(bool(re.search(pattern('any'), output)), bool(expected))
                for kind in ('simplified', 'traditional'):
                    self.assertEqual(bool(re.search(pattern(kind), output)), kind in expected)
                self.assertEqual(annotate(output, desc), output)
                if title.endswith('-GROUP'):
                    self.assertTrue(output.endswith('-GROUP'))

    def test_negative_marker_veto(self):
        self.assertFalse(re.search(pattern('any'), 'Show.CHS.CJKSubNO-GROUP'))
        self.assertIn('CJKSubNO', annotate('Show.CHS-GROUP', '无字幕'))

    def test_hyphenated_quality_without_release_group(self):
        for ending in ('WEB-DL', 'WEB-Rip', 'Blu-Ray', 'DTS-HD', 'HD-DVD'):
            title = 'Example.S01E06.1080p.' + ending
            result = annotate(title, 'CHS')
            self.assertEqual(result, title + '.CJKSubS')
            self.assertEqual(annotate(result, 'CHS'), result)

    def test_rename_markers(self):
        for marker, expected in [('CJKSub', True), ('CJKSubS', True), ('CJKSubT', True), ('CJKSubNO', False)]:
            self.assertEqual(bool(re.search(pattern('any'), 'Show - S01E06 [' + marker + ']')), expected)

    def test_observed_episode_six(self):
        data = json.loads((ROOT / 'cjk/fixtures/doctor-x-e06.json').read_text(encoding='utf-8'))
        admitted = []
        for row in data:
            result = classify(row['title'], row['description'])
            self.assertEqual(result, set(row['expected']))
            if result:
                admitted.append(row['indexerId'])
        self.assertEqual(admitted, [13])

class DatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.baseline = replay(False)
        cls.db = replay()

    @classmethod
    def tearDownClass(cls):
        cls.baseline.close()
        cls.db.close()

    def test_generated_sql_current(self):
        self.assertEqual(OUTPUT.read_text(encoding='utf-8'), generate())

    def test_integrity(self):
        self.assertEqual(self.db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
        self.assertEqual(self.db.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_all_original_rows_unchanged(self):
        # Every upstream row in every table survives byte-for-byte except timestamps
        # produced by independent replay transactions. Nothing is edited or removed.
        for (table,) in self.baseline.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
            columns = [x[1] for x in self.baseline.execute(f'PRAGMA table_info("{table}")')
                       if x[1] not in ('created_at', 'updated_at')]
            selection = ','.join('"' + c + '"' for c in columns)
            before = set(self.baseline.execute(f'SELECT {selection} FROM "{table}"'))
            after = set(self.db.execute(f'SELECT {selection} FROM "{table}"'))
            with self.subTest(table=table):
                self.assertTrue(before <= after)

    def test_new_profile_inherits_quality_and_language(self):
        for table in ('quality_profile_qualities', 'quality_groups', 'quality_group_members', 'quality_profile_languages'):
            columns = [x[1] for x in self.db.execute(f'PRAGMA table_info({table})')
                       if x[1] not in ('id', 'quality_profile_name', 'created_at', 'updated_at')]
            query = f'SELECT {",".join(columns)} FROM {table} WHERE quality_profile_name=?'
            with self.subTest(table=table):
                self.assertEqual(set(self.db.execute(query, (PROFILE,))), set(self.db.execute(query, (BASE,))))

    def test_unknown_cannot_beat_minimum(self):
        minimum = self.db.execute('SELECT minimum_custom_format_score FROM quality_profiles WHERE name=?', (PROFILE,)).fetchone()[0]
        for arr in ('radarr', 'sonarr'):
            scores = self.db.execute("SELECT custom_format_name, score FROM quality_profile_custom_formats WHERE quality_profile_name=? AND arr_type IN ('all', ?)", (PROFILE, arr)).fetchall()
            positives = sum(max(0, s) for _, s in scores)
            penalty = dict(scores)[MISSING]
            self.assertLess(positives + penalty, minimum)
            self.assertEqual(positives + penalty, -1)
            # Worst-case aggregation must also fit Arr's signed 32-bit integer.
            self.assertLess(positives, 2**31)
            self.assertGreater(sum(min(0, s) for _, s in scores), -(2**31))

    def test_preference_and_rename(self):
        scores = dict(self.db.execute("SELECT custom_format_name, score FROM quality_profile_custom_formats WHERE quality_profile_name=? AND arr_type='all'", (PROFILE,)))
        self.assertGreater(scores['CJKSubS'], scores['CJKSubT'])
        for name in ('CJKSub', 'CJKSubS', 'CJKSubT'):
            self.assertEqual(self.db.execute('SELECT include_in_rename FROM custom_formats WHERE name=?', (name,)).fetchone()[0], 1)

    def test_all_embedded_custom_format_examples(self):
        query = '''SELECT t.title, t.should_match, r.pattern, c.negate
          FROM custom_format_tests t JOIN custom_format_conditions c ON c.custom_format_name=t.custom_format_name
          JOIN condition_patterns p ON p.custom_format_name=c.custom_format_name AND p.condition_name=c.name
          JOIN regular_expressions r ON r.name=p.regular_expression_name
          WHERE t.custom_format_name IN ('CJKSub','CJKSubS','CJKSubT',?)'''
        for title, expected, regex, negate in self.db.execute(query, (MISSING,)):
            self.assertEqual(bool(re.search(regex, title)) != bool(negate), bool(expected))

    def test_zero_delay_only_in_local_preset(self):
        row = self.db.execute("SELECT preferred_protocol,usenet_delay,torrent_delay FROM delay_profiles WHERE name='CJK Immediate'").fetchone()
        self.assertEqual(row, ('only_torrent', None, 0))

XML = b'''<rss xmlns:torznab="http://torznab.com/schemas/2015/feed"><channel><item>
<title>Show.S01E06.1080p.WEB-DL-GROUP</title><description>CHS</description>
<guid isPermaLink="false">original-id</guid><link>http://tracker.invalid/details/42</link>
<enclosure url="http://prowlarr.invalid/13/download?apikey=test-only&amp;id=42" length="1234" type="application/x-bittorrent"/>
<torznab:attr name="seeders" value="8"/></item></channel></rss>'''

class XmlTests(unittest.TestCase):
    def test_changes_only_titles(self):
        before, after = ET.fromstring(XML), ET.fromstring(transform(XML))
        title = after.find('./channel/item/title')
        self.assertEqual(title.text, 'Show.S01E06.1080p.WEB-DL.CJKSubS-GROUP')
        title.text = before.findtext('./channel/item/title')
        self.assertEqual(ET.tostring(after), ET.tostring(before))

    def test_capabilities_and_error_unchanged(self):
        for payload in (b'<caps><server title="Prowlarr"/></caps>', b'<error code="100" description="invalid key"/>'):
            self.assertEqual(transform(payload), payload)

    def test_doctype_and_invalid_xml_rejected(self):
        for payload in (b'<!DOCTYPE rss><rss/>', b'not XML', b'<!ENTITY secret "value"><rss/>'):
            with self.assertRaises((ValueError, ET.ParseError)):
                transform(payload)

@contextmanager
def serve(handler):
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}'
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)

class HttpTests(unittest.TestCase):
    def test_proxy_contract(self):
        seen = []
        class Upstream(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass
            def do_GET(self):
                seen.append((self.path, self.headers.get('X-Api-Key')))
                if 'redirect=yes' in self.path:
                    self.send_response(302)
                    self.send_header('Location', '/13/api?t=search&redirected=yes')
                    self.end_headers()
                    return
                if 'error=yes' in self.path:
                    self.send_response(401)
                    self.end_headers()
                    self.wfile.write(b'test-secret-should-not-leak')
                    return
                self.send_response(200)
                self.end_headers()
                self.wfile.write(XML)
        with serve(Upstream) as upstream, serve(make_handler(upstream, {13})) as adapter:
            with urlopen(Request(adapter + '/13/api?t=tvsearch&q=Example&apikey=test-query', headers={'X-Api-Key': 'test-header'})) as res:
                self.assertIn(b'CJKSubS', res.read())
                self.assertEqual(res.status, 200)
            self.assertEqual(seen[-1], ('/13/api?t=tvsearch&q=Example&apikey=test-query', 'test-header'))
            initial = len(seen)
            for path, method, expected in [('/14/api?t=search', 'GET', 404), ('/13/api?t=get', 'GET', 400),
                                           ('/13/api?t=search&t=movie', 'GET', 400), ('/api/v1/command', 'GET', 404),
                                           ('/13/api?t=search', 'POST', 405), ('/13/api?t=search', 'DELETE', 405)]:
                with self.assertRaises(HTTPError) as caught:
                    urlopen(Request(adapter + path, method=method))
                self.assertEqual(caught.exception.code, expected)
                caught.exception.close()
            self.assertEqual(len(seen), initial)
            for query, expected in [('redirect=yes', 502), ('error=yes', 401)]:
                with self.assertRaises(HTTPError) as caught:
                    urlopen(adapter + '/13/api?t=search&' + query)
                self.assertEqual(caught.exception.code, expected)
                self.assertNotIn(b'test-secret', caught.exception.read())
                caught.exception.close()
            self.assertFalse(any('redirected=yes' in path for path, _ in seen))
            with urlopen(adapter + '/health') as res:
                self.assertEqual(res.read(), b'ok')

    def test_configuration_required(self):
        for upstream, ids in [('http://host', set()), ('file:///etc/passwd', {13}), ('http://user:pass@host', {13}), ('http://host?apikey=secret', {13})]:
            with self.assertRaises(ValueError):
                make_handler(upstream, ids)

if __name__ == '__main__':
    unittest.main()
