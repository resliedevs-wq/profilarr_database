"""Read-only Torznab adapter. It never grabs releases or edits an Arr instance."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
import re
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
import xml.etree.ElementTree as ET

try:
    from .evidence import annotate
except ImportError:
    from evidence import annotate

MAX_BYTES = 16 * 1024 * 1024
ET.register_namespace('torznab', 'http://torznab.com/schemas/2015/feed')
ET.register_namespace('newznab', 'http://www.newznab.com/DTD/2010/feeds/attributes/')

def transform(payload):
    if b'<!DOCTYPE' in payload.upper() or b'<!ENTITY' in payload.upper():
        raise ValueError('DTD not supported')
    root = ET.fromstring(payload)
    if root.tag != 'rss':
        return payload  # capabilities / upstream Torznab errors
    for item in root.findall('./channel/item'):
        title = item.find('title')
        if title is None or not title.text:
            continue
        description = item.findtext('description', '')
        title.text = annotate(title.text, description)
    # GUID, download URL, auth query, size, language, categories and flags untouched.
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # never forward API keys to a redirected destination

def make_handler(upstream, allowed_ids):
    u = urlsplit(upstream)
    if u.scheme not in ('http', 'https') or not u.hostname or u.username or u.password or u.query or u.fragment:
        raise ValueError('PROWLARR_URL must be an HTTP(S) base URL without credentials or query')
    if not allowed_ids:
        raise ValueError('Set CJK_INDEXER_IDS explicitly')
    base = upstream.rstrip('/')
    opener = build_opener(NoRedirect())

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # BaseHTTPRequestHandler otherwise logs API keys in query strings.
        def reply(self, status, payload, content_type='text/plain; charset=utf-8'):
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(payload)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(payload)
        def do_GET(self):
            parts = urlsplit(self.path)
            if parts.path == '/health':
                return self.reply(200, b'ok')
            if parts.scheme or parts.netloc:
                return self.reply(400, b'invalid path')
            match = re.fullmatch(r'/(\d+)/api/?', parts.path)
            query = parse_qs(parts.query)
            if not match or int(match[1]) not in allowed_ids:
                return self.reply(404, b'indexer not configured')
            if len(query.get('t', [])) != 1 or query['t'][0] not in ('caps', 'search', 'tvsearch', 'movie'):
                return self.reply(400, b'unsupported read-only query')
            headers = {'Accept': 'application/xml', 'Accept-Encoding': 'identity'}
            if self.headers.get('X-Api-Key'):
                headers['X-Api-Key'] = self.headers['X-Api-Key']
            try:
                req = Request(base + parts.path + '?' + parts.query, headers=headers)
                with opener.open(req, timeout=60) as response:
                    payload = response.read(MAX_BYTES + 1)
                    if len(payload) > MAX_BYTES:
                        raise ValueError('feed too large')
                    result = transform(payload)
                    return self.reply(200, result, 'application/xml; charset=utf-8')
            except HTTPError as e:
                status = e.code if e.code in (401, 403, 429) else 502
                return self.reply(status, b'upstream request failed')
            except (URLError, OSError, ValueError, ET.ParseError):
                return self.reply(502, b'feed unavailable')
        def do_POST(self):
            return self.reply(405, b'read-only adapter')
        do_PUT = do_POST
        do_DELETE = do_POST

    return Handler

def main():
    ids = {int(x.strip()) for x in os.environ.get('CJK_INDEXER_IDS', '').split(',') if x.strip()}
    server = ThreadingHTTPServer(
        (os.environ.get('BIND_HOST', '0.0.0.0'), int(os.environ.get('PORT', '9697'))),
        make_handler(os.environ['PROWLARR_URL'], ids))
    print('CJK Torznab adapter ready', flush=True)
    server.serve_forever()

if __name__ == '__main__':
    main()
