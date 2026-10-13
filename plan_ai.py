"""Responses API calls charged to an explicitly authorized ChatGPT plan.

This is separate from the app's metered OPENAI_API_KEY path. The credential
file is created by scripts/chatgpt_plan_auth.py and kept outside Git.
"""

import fcntl
import json
import os
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


PLAN_SCOPE = "chatgpt.tokens.use.direct"
RESOURCE = "https://api.openai.com/v1"
TOKEN_ENDPOINT = "https://auth.openai.com/api/accounts/oauth/token"


def credential_path(instance_dir):
    return Path(instance_dir) / "chatgpt-plan.json"


def plan_status(instance_dir):
    path = credential_path(instance_dir)
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if PLAN_SCOPE not in record.get("scopes", []) or not record.get("refresh_token"):
        return None
    return {"email": record.get("email", ""), "model": os.getenv("CHATGPT_PLAN_MODEL", "gpt-6-luna")}


def _write_private(path, record):
    fd, temporary = tempfile.mkstemp(prefix=".chatgpt-plan-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(record, handle, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def access_token(instance_dir):
    path = credential_path(instance_dir)
    lock_path = path.with_suffix(".lock")
    if not path.exists():
        raise RuntimeError("ChatGPT Plus 연결 정보가 서버에 없습니다.")
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(fd, "r+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        record = json.loads(path.read_text(encoding="utf-8"))
        if PLAN_SCOPE not in record.get("scopes", []):
            raise RuntimeError("ChatGPT 요금제 사용 권한이 없습니다. 다시 연결해 주세요.")
        if record.get("access_token") and record.get("saved_at", 0) + record.get("expires_in", 0) > time.time() + 120:
            return record["access_token"]
        if not record.get("client_id") or not record.get("refresh_token"):
            raise RuntimeError("ChatGPT 연결을 갱신할 수 없습니다. 다시 연결해 주세요.")
        body = urllib.parse.urlencode({
            "grant_type": "refresh_token",
            "client_id": record["client_id"],
            "refresh_token": record["refresh_token"],
            "resource": RESOURCE,
        }).encode("ascii")
        request = urllib.request.Request(TOKEN_ENDPOINT, data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"})
        try:
            with urllib.request.urlopen(request, timeout=30) as reply:
                refreshed = json.load(reply)
        except (urllib.error.URLError, ValueError) as exc:
            raise RuntimeError("ChatGPT 연결 갱신에 실패했습니다. 다시 연결해 주세요.") from exc
        record.update({
            "access_token": refreshed["access_token"],
            "refresh_token": refreshed.get("refresh_token", record["refresh_token"]),
            "expires_in": int(refreshed.get("expires_in", 3600)),
            "saved_at": time.time(),
        })
        if refreshed.get("scope"):
            record["scopes"] = refreshed["scope"].split()
        if PLAN_SCOPE not in record["scopes"]:
            raise RuntimeError("ChatGPT 요금제 사용 권한이 해제됐습니다.")
        _write_private(path, record)
        return record["access_token"]


def call_plan_ai(instance_dir, input_items, schema, schema_name, instructions):
    if not plan_status(instance_dir):
        raise RuntimeError("ChatGPT Plus가 연결되지 않았습니다.")
    model = os.getenv("CHATGPT_PLAN_MODEL", "gpt-6-luna")
    reasoning_effort = os.getenv("CHATGPT_PLAN_REASONING_EFFORT", "high")
    payload = {
        "model": model,
        "reasoning": {"effort": reasoning_effort},
        "instructions": instructions,
        "input": [{"role": "user", "content": input_items}],
        "text": {"format": {"type": "json_schema", "name": schema_name, "strict": True, "schema": schema}},
        "store": False,
        "stream": True,
    }
    request = urllib.request.Request(RESOURCE + "/responses", data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": "Bearer " + access_token(instance_dir), "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=240) as reply:
            chunks = []
            completed = None
            for line in reply:
                if not line.startswith(b"data: "):
                    continue
                event = json.loads(line[6:])
                kind = event.get("type")
                if kind == "response.output_text.delta":
                    chunks.append(event.get("delta", ""))
                elif kind == "response.failed":
                    error = (event.get("response") or {}).get("error") or {}
                    code = error.get("code", "unknown_error")
                    raise RuntimeError("ChatGPT 요청 실패: " + code)
                elif kind == "response.incomplete":
                    raise RuntimeError("ChatGPT 응답이 완료되지 않았습니다. 다시 시도해 주세요.")
                elif kind == "response.completed":
                    completed = event.get("response") or {}
            if completed is None:
                raise RuntimeError("ChatGPT 응답이 끝까지 도착하지 않았습니다.")
    except urllib.error.HTTPError as exc:
        try:
            error = json.loads(exc.read().decode("utf-8")).get("error", {})
            detail = str(error.get("message") or error.get("code") or "")[:240]
        except (ValueError, UnicodeDecodeError):
            detail = ""
        raise RuntimeError(f"ChatGPT 요청이 거부됐습니다 (HTTP {exc.code}). {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError("ChatGPT 서비스에 연결할 수 없습니다.") from exc
    raw = "".join(chunks)
    if not raw:
        raw = "".join(part.get("text", "") for item in completed.get("output", [])
            if item.get("type") == "message" for part in item.get("content", [])
            if part.get("type") == "output_text")
    if not raw:
        raise RuntimeError("ChatGPT 응답에 정리된 내용이 없습니다.")
    try:
        return json.loads(raw), completed.get("usage", {}), model
    except ValueError as exc:
        raise RuntimeError("ChatGPT 응답을 읽을 수 없습니다. 다시 시도해 주세요.") from exc
