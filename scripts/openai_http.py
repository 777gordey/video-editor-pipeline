"""Общий POST к OpenAI Responses API: лог тела ошибки + ретраи 429/5xx."""
import re
import sys
import time

import requests

ATTEMPTS = 3
MAX_WAIT = 60.0


def _error_info(resp):
    try:
        err = resp.json().get("error") or {}
        return err.get("type"), err.get("code")
    except ValueError:
        return None, None


def _wait_seconds(resp, attempt: int) -> float:
    try:
        return min(float(resp.headers["Retry-After"]), MAX_WAIT)
    except (KeyError, ValueError):
        return min(2.0 * 2 ** attempt, MAX_WAIT)


def openai_post(payload: dict, api_key: str, timeout: int = 60) -> requests.Response:
    """POST /v1/responses. Не-2xx: печатает статус и тело ошибки (ключ не
    печатается), 429/5xx ретраит (3 попытки, экспоненциальная пауза или
    Retry-After), insufficient_quota не ретраит. После неудачи поднимает
    requests.HTTPError."""
    for attempt in range(ATTEMPTS):
        resp = requests.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=timeout,
        )
        if resp.ok:
            return resp
        etype, ecode = _error_info(resp)
        body = re.sub(r"sk-[A-Za-z0-9_*.\-]+", "sk-***", resp.text)[:1500]
        print(f"[openai] HTTP {resp.status_code} (попытка {attempt + 1}/{ATTEMPTS}) "
              f"type={etype} code={ecode} body={body}", file=sys.stderr)
        quota = "insufficient_quota" in (etype, ecode)
        retryable = resp.status_code == 429 or resp.status_code >= 500
        if quota or not retryable or attempt == ATTEMPTS - 1:
            break
        wait = _wait_seconds(resp, attempt)
        print(f"[openai] повтор через {wait:.0f}с", file=sys.stderr)
        time.sleep(wait)
    resp.raise_for_status()
    return resp
