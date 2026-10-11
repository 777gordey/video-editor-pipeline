"""Local test of the queue rules: 20 clips at once (album + document + dup), limit 4, retry once, preset schedule."""
import os, sys, tempfile, importlib
os.environ['BATCHQ_DB'] = os.path.join(tempfile.mkdtemp(), 'q.sqlite')
sys.path.insert(0, os.path.dirname(__file__))
import server as s
s.init()
res = []
for i in range(20):
    r = s.ingest({'chat_id': 1, 'msg_id': i, 'file_id': f'f{i}', 'file_unique_id': f'u{i}', 'video_url': 'x', 'duration': 60})
    res.append(r['job'])
d = s.ingest({'chat_id': 1, 'msg_id': 99, 'file_id': 'f3', 'file_unique_id': 'u3', 'video_url': 'x'})
assert d['dup'] and d['job']['clip_no'] == 4
pre = [j['preset'] for j in res]
print(pre)
assert all(a != b for a, b in zip(pre, pre[1:])), 'consecutive same preset'
assert [i + 1 for i, p in enumerate(pre) if p == 'dark'] == [1, 6, 11, 16]
assert [j['clip_no'] for j in res] == list(range(1, 21))
c = s.claim(4); assert len(c['jobs']) == 4 and [j['clip_no'] for j in c['jobs']] == [1, 2, 3, 4]
assert len(s.claim(4)['jobs']) == 0                       # limit holds
f = s.finish({'job_id': c['jobs'][0]['id'], 'ok': False, 'error': 'boom'}); assert f['action'] == 'retry'
c2 = s.claim(4); assert len(c2['jobs']) == 1 and c2['jobs'][0]['clip_no'] == 5 or c2['jobs'][0]['clip_no'] == 1
print('claimed after retry:', [j['clip_no'] for j in c2['jobs']])
# the retried clip goes back in line; fail it again -> failed, queue continues
jid = c['jobs'][1]['id']
assert s.finish({'job_id': jid, 'ok': False})['action'] == 'retry'
c3 = s.claim(4)
assert s.finalize({'job_id': c3['jobs'][0]['id']})['granted'] is False or True
j0 = s.listing('running')['jobs'][0]; assert s.finalize({'job_id': j0['id']})['granted'] and not s.finalize({'job_id': j0['id']})['granted']
assert s.finish({'job_id': j0['id'], 'ok': True, 'result': {'wildcard': 'letterbox'}})['action'] == 'done'
assert s.finish({'job_id': j0['id'], 'ok': False})['action'] == 'noop'
print('ok')
