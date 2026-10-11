#!/usr/bin/env python3
"""Generates the three batch n8n workflows (sanitized: placeholders for credential ids / secrets).
  ingest     Telegram Trigger (or test Webhook)  -> media extraction (video | document | album item) -> /ingest on the queue
  dispatcher Schedule 30 s -> /claim (limit 4) -> GitHub workflow_dispatch -> /finish on dispatch error
  watcher    Schedule 45 s -> /running -> find the run by job_id -> done: /finalize, download artifact, send to Telegram, /finish ; failed: /finish (retry once, then a short message)
usage: make.py OUT_DIR"""
import json, sys, uuid
from pathlib import Path

Q = "http://batchq:8099"
GH = "https://api.github.com/repos/{{$env.GITHUB_OWNER}}/{{$env.GITHUB_REPO}}"
IDS = {}


def nid():
    return str(uuid.uuid4())


def node(name, typ, ver, params, pos, cred=None, **extra):
    n = {"parameters": params, "id": nid(), "name": name, "type": typ, "typeVersion": ver, "position": pos}
    if cred == "gh":
        n["credentials"] = {"githubApi": {"id": "__GITHUB_CRED_ID__", "name": "GitHub Token (repo scope)"}}
    if cred == "tg":
        n["credentials"] = {"telegramApi": {"id": "__TELEGRAM_CRED_ID__", "name": "Video Pipeline Bot"}}
    n.update(extra)
    return n


def code(name, js, pos):
    return node(name, "n8n-nodes-base.code", 2, {"jsCode": js}, pos)


def qpost(name, path, body_expr, pos, **kw):
    return node(name, "n8n-nodes-base.httpRequest", 4.2, {
        "method": "POST", "url": f"{Q}{path}", "sendHeaders": True,
        "headerParameters": {"parameters": [{"name": "X-Q-Key", "value": "__BATCHQ_KEY__"}]},
        "sendBody": True, "specifyBody": "json", "jsonBody": body_expr, "options": {"timeout": 20000}}, pos, **kw)


def qget(name, path, pos):
    return node(name, "n8n-nodes-base.httpRequest", 4.2, {
        "method": "GET", "url": f"{Q}{path}", "sendHeaders": True,
        "headerParameters": {"parameters": [{"name": "X-Q-Key", "value": "__BATCHQ_KEY__"}]}, "options": {"timeout": 20000}}, pos)


def gh_get(name, url, pos, **opts):
    return node(name, "n8n-nodes-base.httpRequest", 4.2, {"method": "GET", "url": url, "authentication": "predefinedCredentialType",
                                                         "nodeCredentialType": "githubApi", "options": opts}, pos, cred="gh")


def tg(name, chat, text, pos):
    return node(name, "n8n-nodes-base.telegram", 1.2, {"chatId": chat, "text": text, "additionalFields": {}}, pos, cred="tg")


def if_bool(name, expr, pos):
    return node(name, "n8n-nodes-base.if", 2.2, {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict"},
                "conditions": [{"id": nid(), "leftValue": expr, "rightValue": True, "operator": {"type": "boolean", "operation": "true"}}], "combinator": "and"}}, pos)


def _fix(v, key=None):
    if isinstance(v, dict):
        return {k: _fix(x, k) for k, x in v.items()}
    if isinstance(v, list):
        return [_fix(x, key) for x in v]
    if isinstance(v, str) and key not in ("jsCode",) and "{{" in v and not v.startswith("="):
        return "=" + v
    return v


def wf(name, nodes, conns, trigger_name):
    nodes = [dict(n, parameters=_fix(n["parameters"])) for n in nodes]
    c = {}
    for a, outs in conns.items():
        c[a] = {"main": [[{"node": b, "type": "main", "index": 0} for b in out] for out in outs]}
    return {"name": name, "nodes": nodes, "connections": c, "settings": {"executionOrder": "v1"}, "active": False}


def ingest(test):
    EXTRACT = r"""
const upd = ($json.body && $json.body.message) ? $json.body : $json;
const m = upd.message || {};
if (!m.from || String(m.from.id) !== String($env.ALLOWED_USER_ID)) return [];
let v = null, kind = '';
if (m.video) { v = m.video; kind = 'video'; }
else if (m.video_note) { v = m.video_note; kind = 'video_note'; }
else if (m.document && ((m.document.mime_type || '').startsWith('video/') || /\.(mp4|mov|m4v|mkv|webm|avi|3gp)$/i.test(m.document.file_name || ''))) { v = m.document; kind = 'document'; }
if (!v) return [];
return [{ json: { chat_id: m.chat.id, msg_id: m.message_id, media_group_id: m.media_group_id || '', kind, file_id: v.file_id,
  file_unique_id: v.file_unique_id, duration: v.duration || 0, caption: String(m.caption || '').slice(0, 1500), test_url: m.test_video_url || '' } }];
"""
    nodes, conns = [], {}
    if test:
        nodes.append(node("Test webhook", "n8n-nodes-base.webhook", 2, {"httpMethod": "POST", "path": "__TEST_PATH__", "responseMode": "onReceived", "options": {}}, [0, 0], webhookId=nid()))
    else:
        nodes.append(node("Telegram Trigger", "n8n-nodes-base.telegramTrigger", 1.1, {"updates": ["message"]}, [0, 0], cred="tg", webhookId=nid()))
    trig = nodes[0]["name"]
    nodes += [
        code("Extract media", EXTRACT, [220, 0]),
        if_bool("Too long?", "={{ $json.duration > 180 }}", [440, 0]),
        tg("Reject long", "={{$json.chat_id}}", "=Клип длиннее 3 минут не беру (макс. 2-3 мин). Пришлите покороче.", [660, -120]),
        if_bool("Has test url?", "={{ !!$json.test_url }}", [660, 80]),
        node("Telegram getFile", "n8n-nodes-base.httpRequest", 4.2, {"method": "GET", "url": "=http://telegram-bot-api:8081/bot{{$env.TELEGRAM_BOT_TOKEN}}/getFile?file_id={{$json.file_id}}", "options": {"timeout": 600000}}, [880, 160]),
        code("Compose ingest", r"""
const e = $('Extract media').first().json;
let url = e.test_url;
if (!url) { const fp = ($json.result && $json.result.file_path) || ''; url = 'https://gordey1-bot.duckdns.org/vf/__VF_SECRET__/' + fp.split('/').pop(); }
return [{ json: { chat_id: e.chat_id, msg_id: e.msg_id, media_group_id: e.media_group_id, file_id: e.file_id, file_unique_id: e.file_unique_id, duration: e.duration, caption: e.caption, video_url: url } }];
""", [1100, 80]),
        qpost("Ingest", "/ingest", "={{ JSON.stringify($json) }}", [1320, 80]),
        if_bool("Duplicate?", "={{ $json.dup }}", [1540, 80]),
        tg("Dup notice", "={{$json.job.chat_id}}", "=Клип уже в работе или обработан (№ {{ String($json.job.clip_no).padStart(2,'0') }}), второй раз не беру.", [1760, -20]),
        if_bool("First of batch?", "={{ $json.job.clip_no === 1 }}", [1760, 200]),
        tg("Batch started", "={{$json.job.chat_id}}", "Принял. Клипы нумеруются по порядку прихода, готовые пришлю по мере монтажа (одновременно монтируется до 4).", [1980, 200]),
    ]
    conns = {trig: [["Extract media"]], "Extract media": [["Too long?"]], "Too long?": [["Reject long"], ["Has test url?"]],
             "Has test url?": [["Compose ingest"], ["Telegram getFile"]], "Telegram getFile": [["Compose ingest"]], "Compose ingest": [["Ingest"]],
             "Ingest": [["Duplicate?"]], "Duplicate?": [["Dup notice"], ["First of batch?"]], "First of batch?": [["Batch started"], []]}
    return wf("Batch ingest" + (" TEST (webhook)" if test else " (Telegram)"), nodes, conns, trig)


def dispatcher():
    nodes = [
        node("Every 30 s", "n8n-nodes-base.scheduleTrigger", 1.2, {"rule": {"interval": [{"field": "seconds", "secondsInterval": 30}]}}, [0, 0]),
        qpost("Claim", "/claim", '={{ JSON.stringify({ limit: 4 }) }}', [220, 0]),
        code("Split jobs", "return ($json.jobs || []).map(j => ({ json: j }));", [440, 0]),
        node("Dispatch run", "n8n-nodes-base.httpRequest", 4.2, {
            "method": "POST", "url": f"{GH}/actions/workflows/batch-edit.yml/dispatches", "authentication": "predefinedCredentialType", "nodeCredentialType": "githubApi",
            "sendHeaders": True, "headerParameters": {"parameters": [{"name": "Accept", "value": "application/vnd.github+json"}]},
            "sendBody": True, "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify({ ref: 'batch-engine', inputs: { job_id: $json.id, video_url: $json.video_url, preset: $json.preset, clip_no: String($json.clip_no), seed: String($json.seed), recent: ($json.recent_wildcards || []).join(',') } }) }}",
            "options": {"response": {"response": {"fullResponse": True, "neverError": True}}}}, [660, 0], cred="gh"),
        if_bool("Dispatch ok?", "={{ $json.statusCode < 300 }}", [880, 0]),
        qpost("Dispatch failed", "/finish", "={{ JSON.stringify({ job_id: $('Split jobs').item.json.id, ok: false, error: 'dispatch http ' + $json.statusCode }) }}", [1100, 120]),
        if_bool("Gave up?", "={{ $json.action === 'failed' }}", [1320, 120]),
        tg("Dispatch gave up", "={{$json.job.chat_id}}", "=Клип {{ String($json.job.clip_no).padStart(2,'0') }} из {{ $json.total }}: не удалось запустить монтаж. Очередь идёт дальше.", [1540, 60]),
    ]
    conns = {"Every 30 s": [["Claim"]], "Claim": [["Split jobs"]], "Split jobs": [["Dispatch run"]], "Dispatch run": [["Dispatch ok?"]],
             "Dispatch ok?": [[], ["Dispatch failed"]], "Dispatch failed": [["Gave up?"]], "Gave up?": [["Dispatch gave up"], []]}
    return wf("Batch dispatcher", nodes, conns, "Every 30 s")


def watcher():
    MATCH = r"""
const job = $('Split running').item.json;
const runs = $json.workflow_runs || [];
const r = runs.find(x => (x.display_title || '').includes(job.id));
const ageMin = (Date.now() / 1000 - job.started) / 60;
if (!r) { return ageMin > 8 ? [{ json: { job, state: 'lost', run_url: '' } }] : []; }
if (r.status !== 'completed') return [];
const ok = r.conclusion === 'success';
return [{ json: { job, state: ok ? 'success' : 'failed', run_id: r.id, run_url: r.html_url, conclusion: r.conclusion } }];
"""
    PICK = r"""
const f = $('Match run').first().json;
const job = f.job;
const item = $input.first();
const by = {}, key = {};
for (const [k, b] of Object.entries(item.binary || {})) { by[b.fileName] = b; key[b.fileName] = k; }
const video = by['final.mp4'];
if (!video) throw new Error('final.mp4 not found: ' + Object.keys(by).join(','));
let res = {};
try { res = JSON.parse((await this.helpers.getBinaryDataBuffer(0, key['result.json'])).toString('utf8')); } catch (e) {}
const NAMES = { dark: 'Dark Steel', proof: 'Proof Cards', slab: 'Hazard Slab' };
const num = String(job.clip_no).padStart(2, '0');
const cap = `Клип ${num} из ${job.total} · ${NAMES[res.preset || job.preset] || job.preset}` + (res.wildcard ? ` · фишка: ${res.wildcard}` : '');
return [{ json: { caption: cap, result: res }, binary: { data: video } }];
"""
    nodes = [
        node("Every 45 s", "n8n-nodes-base.scheduleTrigger", 1.2, {"rule": {"interval": [{"field": "seconds", "secondsInterval": 45}]}}, [0, 0]),
        qget("Running jobs", "/running", [220, 0]),
        code("Split running", "return ($json.jobs || []).map(j => ({ json: j }));", [440, 0]),
        gh_get("List runs", f"{GH}/actions/workflows/batch-edit.yml/runs?per_page=50", [660, 0]),
        code("Match run", MATCH, [880, 0]),
        qpost("Finalize", "/finalize", "={{ JSON.stringify({ job_id: $json.job.id }) }}", [1100, 0]),
        if_bool("Granted?", "={{ $json.granted }}", [1320, 0]),
        if_bool("Success?", "={{ $('Match run').item.json.state === 'success' }}", [1540, 0]),
        # failure branch
        qpost("Finish failed", "/finish", "={{ JSON.stringify({ job_id: $('Match run').item.json.job.id, ok: false, error: $('Match run').item.json.state + ' ' + ($('Match run').item.json.conclusion || ''), run_url: $('Match run').item.json.run_url }) }}", [1760, 200]),
        if_bool("Gave up?", "={{ $json.action === 'failed' }}", [1980, 200]),
        tg("Failure notice", "={{$json.job.chat_id}}", "=Клип {{ String($json.job.clip_no).padStart(2,'0') }} из {{ $json.total }}: монтаж не удался даже со второй попытки. Лог: {{$json.job.run_url}}. Остальные продолжаются.", [2200, 140]),
        # success branch
        gh_get("List artifacts", f"{GH}/actions/runs/{{{{$('Match run').item.json.run_id}}}}/artifacts", [1760, -160]),
        code("Pick final artifact", "const a = ($json.artifacts || []).find(x => x.name === 'final' && !x.expired);\nif (!a) throw new Error('no final artifact');\nreturn [{ json: { artifact_id: a.id } }];", [1980, -160]),
        node("Artifact URL", "n8n-nodes-base.httpRequest", 4.2, {"method": "GET", "url": f"{GH}/actions/artifacts/{{{{$json.artifact_id}}}}/zip", "authentication": "predefinedCredentialType", "nodeCredentialType": "githubApi",
                                                                  "options": {"redirect": {"redirect": {"followRedirects": False}}, "response": {"response": {"fullResponse": True, "neverError": True}}}}, [2200, -160], cred="gh"),
        node("Download zip", "n8n-nodes-base.httpRequest", 4.2, {"method": "GET", "url": "={{$json.headers.location}}", "authentication": "none",
                                                                "options": {"response": {"response": {"responseFormat": "file"}}, "timeout": 900000}}, [2420, -160]),
        node("Unzip", "n8n-nodes-base.compression", 1.1, {"operation": "decompress", "fileName": "data"}, [2640, -160]),
        code("Pick files", PICK, [2860, -160]),
        node("Send video", "n8n-nodes-base.telegram", 1.2, {"operation": "sendVideo", "chatId": "={{$('Match run').item.json.job.chat_id}}", "binaryData": True, "binaryPropertyName": "data",
                                                            "additionalFields": {"caption": "={{$json.caption}}"}}, [3080, -160], cred="tg", retryOnFail=True, maxTries=3, waitBetweenTries=5000),
        qpost("Finish ok", "/finish", "={{ JSON.stringify({ job_id: $('Match run').item.json.job.id, ok: true, result: $('Pick files').item.json.result, run_url: $('Match run').item.json.run_url }) }}", [3300, -160]),
    ]
    conns = {"Every 45 s": [["Running jobs"]], "Running jobs": [["Split running"]], "Split running": [["List runs"]], "List runs": [["Match run"]],
             "Match run": [["Finalize"]], "Finalize": [["Granted?"]], "Granted?": [["Success?"], []], "Success?": [["List artifacts"], ["Finish failed"]],
             "Finish failed": [["Gave up?"]], "Gave up?": [["Failure notice"], []],
             "List artifacts": [["Pick final artifact"]], "Pick final artifact": [["Artifact URL"]], "Artifact URL": [["Download zip"]], "Download zip": [["Unzip"]],
             "Unzip": [["Pick files"]], "Pick files": [["Send video"]], "Send video": [["Finish ok"]]}
    return wf("Batch watcher", nodes, conns, "Every 45 s")


if __name__ == "__main__":
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    for name, w in (("ingest_telegram", ingest(False)), ("ingest_test", ingest(True)), ("dispatcher", dispatcher()), ("watcher", watcher())):
        (out / f"{name}.workflow.json").write_text(json.dumps(w, ensure_ascii=False, indent=1), encoding="utf-8")
        print(name, len(w["nodes"]), "nodes")
