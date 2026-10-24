"""Conservative subtitle claims, shared by the feed adapter and SQL generator."""
import html
import json
from html.parser import HTMLParser
from pathlib import Path
import re

POLICY = json.loads(Path(__file__).with_name('policy.json').read_text(encoding='utf-8'))
POLICY['negative'] = (r'(?:\bCJKSubNO\b|(?:没有|沒有|不含|不带|不帶)(?:中文|简体|簡體|繁体|繁體|中英)?字幕|'
                      r'\bchinese[ ._-]+(?:subtitles?|subs?)\s*:\s*(?:no|none)\b|'
                      r'(?:中文字幕|简体字幕|繁體字幕|繁体字幕|簡體字幕)\s*(?:待发布|待發佈|待制作|制作中|製作中)|'
                      + POLICY['negative'] + ')')
FLAGS = re.IGNORECASE | re.DOTALL

class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = 0
    def handle_starttag(self, tag, attrs):
        if tag.lower() in ('script', 'style'):
            self.hidden += 1
        if not self.hidden:
            self.parts.append(' ')
    def handle_endtag(self, tag):
        if tag.lower() in ('script', 'style'):
            self.hidden = max(0, self.hidden - 1)
        if not self.hidden:
            self.parts.append(' ')
    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)

def text_only(value):
    parser = _Text()
    parser.feed(html.unescape(value or ''))
    return ' '.join(''.join(parser.parts).split())

def classify(title, description=''):
    text = title + ' ' + text_only(description)
    if re.search(POLICY['negative'], text, FLAGS):
        return set()
    kinds = {k for k in ('simplified', 'traditional', 'unspecified')
             if re.search(POLICY[k], text, FLAGS)}
    if 'simplified' in kinds or 'traditional' in kinds:
        kinds.discard('unspecified')
    return kinds

def pattern(kind):
    """Same regex syntax supported by Python and .NET; negatives always veto."""
    body = '|'.join(POLICY[k] for k in ('simplified', 'traditional', 'unspecified')) if kind == 'any' else POLICY[kind]
    return '(?is)^(?!.*' + POLICY['negative'] + ').*(?:' + body + ')'

def annotate(title, description=''):
    # Remove adapter markers first: contradictory descriptions must revoke them.
    clean = re.sub(r'(?i)[ .]?(?<![A-Za-z0-9])CJKSub(?:NO|S|T|U)?(?![A-Za-z0-9])', '', title)
    kinds = classify(title, description)
    negative = re.search(POLICY['negative'], title + ' ' + text_only(description), FLAGS)
    if not kinds and not negative:
        return clean
    # Keep negative description evidence visible to Arr even if the title says CHS.
    markers = 'CJKSubNO' if negative else '.'.join(POLICY['markers'][k] for k in sorted(kinds))
    # Keep the original release group at the end. No audio-language tokens added.
    group = re.search(r'-[A-Za-z0-9][A-Za-z0-9_]*$', clean)
    if re.search(r'(?i)(?:WEB-(?:DL|RIP)|BLU-RAY|DTS-HD|HD-DVD)$', clean):
        group = None  # A hyphenated quality/audio token is not a release group.
    if group:
        return clean[:group.start()].rstrip(' .') + '.' + markers + clean[group.start():]
    return clean.rstrip(' .') + '.' + markers
