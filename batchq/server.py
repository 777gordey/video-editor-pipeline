#!/usr/bin/env python3
"""Tiny queue service for the batch video machine (stdlib only, sqlite). One place for state that must be atomic:
dedupe by Telegram file_unique_id, arrival numbering ("clip 01 of N"), preset schedule, concurrency limit, one retry.
Runs next to n8n on the VPS; n8n talks to it over the docker network with a shared key."""
import json, os, sqlite3, threading, time, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DB = os.environ.get('BATCHQ_DB', '/data/q.sqlite')
KEY = os.environ.get('BATCHQ_KEY', '')
GAP = int(os.environ.get('BATCHQ_GAP_SEC', '240'))            # clips arriving within this gap of the previous one belong to the same batch
MAX_ATTEMPTS = 2                                              # first try + one retry
RUN_TIMEOUT = int(os.environ.get('BATCHQ_RUN_TIMEOUT_SEC', str(110 * 60)))
LOCK = threading.Lock()


def preset_for(clip_no, prev):
    """dark moody on clips 1,6,11,16,...; proof/slab alternate in between; never the same preset twice in a row"""
    if (clip_no - 1) % 5 == 0:
        p = 'dark'
    else:
        order = ['proof', 'slab']
        p = order[(clip_no - 2) % 2] if prev not in order else ('slab' if prev == 'proof' else 'proof')
        if p == prev:
            p = 'slab' if p == 'proof' else 'proof'
    if p == prev:
        p = next(x for x in ('dark', 'proof', 'slab') if x != prev)
    return p


def db():
    c = sqlite3.connect(DB, timeout=30, isolation_level=None)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA journal_mode=WAL')
    return c


def init():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    c = db()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS batches(id TEXT PRIMARY KEY, chat_id TEXT, created REAL, last_arrival REAL, count INTEGER DEFAULT 0, last_preset TEXT);
    CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, batch_id TEXT, clip_no INTEGER, chat_id TEXT, msg_id INTEGER, media_group_id TEXT,
      file_id TEXT, file_unique_id TEXT UNIQUE, video_url TEXT, duration REAL, caption TEXT, preset TEXT, seed TEXT,
      status TEXT, attempts INTEGER DEFAULT 0, created REAL, started REAL, finished REAL, run_id TEXT, run_url TEXT, error TEXT, result TEXT, wildcard TEXT);
    CREATE INDEX IF NOT EXISTS jobs_status ON jobs(status);
    """)
    c.close()


def row(r):
    return dict(r) if r else None


def ingest(b):
    now = time.time()
    c = db()
    try:
        old = c.execute('SELECT * FROM jobs WHERE file_unique_id=?', (b['file_unique_id'],)).fetchone()
        if old:
            return {'dup': True, 'job': row(old)}
        chat = str(b['chat_id'])
        bt = c.execute('SELECT * FROM batches WHERE chat_id=? ORDER BY created DESC LIMIT 1', (chat,)).fetchone()
        if not bt or now - bt['last_arrival'] > GAP:
            bid = 'b' + uuid.uuid4().hex[:8]
            c.execute('INSERT INTO batches(id,chat_id,created,last_arrival,count) VALUES(?,?,?,?,0)', (bid, chat, now, now))
            bt = c.execute('SELECT * FROM batches WHERE id=?', (bid,)).fetchone()
        n = bt['count'] + 1
        preset = preset_for(n, bt['last_preset'])
        jid = f"j{int(now)}{uuid.uuid4().hex[:5]}"
        c.execute('INSERT INTO jobs(id,batch_id,clip_no,chat_id,msg_id,media_group_id,file_id,file_unique_id,video_url,duration,caption,preset,seed,status,created) '
                  'VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                  (jid, bt['id'], n, chat, b.get('msg_id'), b.get('media_group_id'), b.get('file_id'), b['file_unique_id'], b.get('video_url'),
                   b.get('duration'), (b.get('caption') or '')[:1500], preset, str(uuid.uuid4().int % 100000), 'queued', now))
        c.execute('UPDATE batches SET count=?, last_arrival=?, last_preset=? WHERE id=?', (n, now, preset, bt['id']))
        return {'dup': False, 'job': row(c.execute('SELECT * FROM jobs WHERE id=?', (jid,)).fetchone()), 'total': n}
    finally:
        c.close()


def total_of(c, batch_id):
    return c.execute('SELECT count FROM batches WHERE id=?', (batch_id,)).fetchone()['count']


def claim(limit):
    now = time.time()
    c = db()
    try:
        for r in c.execute("SELECT * FROM jobs WHERE status='running' AND started<?", (now - RUN_TIMEOUT,)).fetchall():
            _finish(c, r['id'], False, 'run timeout (watchdog)', None, None)
        running = c.execute("SELECT COUNT(*) n FROM jobs WHERE status='running'").fetchone()['n']
        out = []
        while running + len(out) < limit:
            r = c.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY created, clip_no LIMIT 1").fetchone()
            if not r:
                break
            c.execute("UPDATE jobs SET status='running', attempts=attempts+1, started=?, run_id=NULL, run_url=NULL, error=NULL WHERE id=?", (now, r['id']))
            j = row(c.execute('SELECT * FROM jobs WHERE id=?', (r['id'],)).fetchone())
            recent = [x['wildcard'] for x in c.execute("SELECT wildcard FROM jobs WHERE batch_id=? AND wildcard IS NOT NULL AND wildcard<>'' ORDER BY clip_no DESC LIMIT 4", (r['batch_id'],))]
            j['recent_wildcards'] = recent
            j['total'] = total_of(c, r['batch_id'])
            out.append(j)
        return {'jobs': out, 'running': running + len(out)}
    finally:
        c.close()


def _finish(c, jid, ok, error, result, run_url):
    r = c.execute('SELECT * FROM jobs WHERE id=?', (jid,)).fetchone()
    if not r:
        return {'action': 'unknown'}
    now = time.time()
    if ok:
        wc = (result or {}).get('wildcard') if isinstance(result, dict) else None
        c.execute("UPDATE jobs SET status='done', finished=?, result=?, wildcard=?, run_url=COALESCE(?,run_url) WHERE id=?",
                  (now, json.dumps(result, ensure_ascii=False) if result else None, wc, run_url, jid))
        return {'action': 'done', 'job': row(c.execute('SELECT * FROM jobs WHERE id=?', (jid,)).fetchone()), 'total': total_of(c, r['batch_id'])}
    if r['attempts'] < MAX_ATTEMPTS:
        c.execute("UPDATE jobs SET status='queued', error=?, run_url=COALESCE(?,run_url) WHERE id=?", ((error or '')[:300], run_url, jid))
        return {'action': 'retry', 'job': row(c.execute('SELECT * FROM jobs WHERE id=?', (jid,)).fetchone()), 'total': total_of(c, r['batch_id'])}
    c.execute("UPDATE jobs SET status='failed', finished=?, error=?, run_url=COALESCE(?,run_url) WHERE id=?", (now, (error or '')[:300], run_url, jid))
    return {'action': 'failed', 'job': row(c.execute('SELECT * FROM jobs WHERE id=?', (jid,)).fetchone()), 'total': total_of(c, r['batch_id'])}


def finish(b):
    c = db()
    try:
        return _finish(c, b['job_id'], bool(b.get('ok')), b.get('error'), b.get('result'), b.get('run_url'))
    finally:
        c.close()


def update(b):
    c = db()
    try:
        c.execute('UPDATE jobs SET run_id=COALESCE(?,run_id), run_url=COALESCE(?,run_url) WHERE id=?', (b.get('run_id'), b.get('run_url'), b['job_id']))
        return {'ok': True}
    finally:
        c.close()


def listing(status=None):
    c = db()
    try:
        q = 'SELECT * FROM jobs' + (' WHERE status=?' if status else '') + ' ORDER BY created, clip_no'
        rows = [row(r) for r in c.execute(q, (status,) if status else ())]
        for r in rows:
            r.pop('result', None)
        return {'jobs': rows}
    finally:
        c.close()


def stats(chat=None):
    c = db()
    try:
        s = {r['status']: r['n'] for r in c.execute('SELECT status, COUNT(*) n FROM jobs GROUP BY status')}
        return {'counts': s, 'batches': [row(r) for r in c.execute('SELECT * FROM batches ORDER BY created DESC LIMIT 10')]}
    finally:
        c.close()


def purge(prefix):
    c = db()
    try:
        ids = [r['id'] for r in c.execute("SELECT id FROM jobs WHERE video_url LIKE ?", (prefix + '%',))]
        c.execute("DELETE FROM jobs WHERE video_url LIKE ?", (prefix + '%',))
        c.execute('DELETE FROM batches WHERE id NOT IN (SELECT batch_id FROM jobs)')
        return {'deleted': len(ids)}
    finally:
        c.close()


class H(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        b = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _auth(self):
        if KEY and self.headers.get('X-Q-Key') != KEY:
            self._send(401, {'error': 'unauthorized'})
            return False
        return True

    def do_GET(self):
        if not self._auth():
            return
        with LOCK:
            if self.path.startswith('/running'):
                return self._send(200, listing('running'))
            if self.path.startswith('/jobs'):
                return self._send(200, listing())
            if self.path.startswith('/stats'):
                return self._send(200, stats())
        self._send(404, {'error': 'not found'})

    def do_POST(self):
        if not self._auth():
            return
        n = int(self.headers.get('Content-Length') or 0)
        try:
            b = json.loads(self.rfile.read(n) or b'{}')
        except ValueError:
            return self._send(400, {'error': 'bad json'})
        try:
            with LOCK:
                if self.path == '/ingest':
                    return self._send(200, ingest(b))
                if self.path == '/claim':
                    return self._send(200, claim(int(b.get('limit', 4))))
                if self.path == '/finish':
                    return self._send(200, finish(b))
                if self.path == '/update':
                    return self._send(200, update(b))
                if self.path == '/purge':
                    return self._send(200, purge(b.get('prefix', '@@none@@')))
        except Exception as e:                                        # noqa
            return self._send(500, {'error': f'{type(e).__name__}: {e}'})
        self._send(404, {'error': 'not found'})

    def log_message(self, *a):
        pass


if __name__ == '__main__':
    init()
    ThreadingHTTPServer(('0.0.0.0', int(os.environ.get('PORT', '8099'))), H).serve_forever()
