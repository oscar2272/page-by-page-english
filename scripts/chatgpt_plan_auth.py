"""Owner-only, local-loopback Sign in with ChatGPT registration.

Run on the owner's computer. Credentials stay in the Git-ignored instance directory.
The resulting credential file may later be transferred to the owner's VM over SSH.
"""

import argparse
import base64
import hashlib
import json
import os
import secrets
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import jwt


ROOT = Path(__file__).resolve().parents[1]
CREDENTIALS = ROOT / "instance" / "chatgpt-plan.json"
ISSUER = "https://auth.openai.com"
RESOURCE = "https://api.openai.com/v1"
SCOPE = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"
CALLBACK_PATH = "/auth/callback"
APP_NAME = "Page by Page English"


def request_json(url, *, data=None, headers=None):
    request = urllib.request.Request(url, data=data, headers=headers or {}, method="POST" if data is not None else "GET")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def save_private(record):
    CREDENTIALS.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".chatgpt-plan-", dir=CREDENTIALS.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(record, handle, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, CREDENTIALS)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load_private():
    if not CREDENTIALS.exists():
        return {}
    return json.loads(CREDENTIALS.read_text(encoding="utf-8"))


def exchange_token(fields):
    return request_json(
        ISSUER + "/api/accounts/oauth/token",
        data=urllib.parse.urlencode(fields).encode("ascii"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )


def validate_id_token(token, client_id, nonce):
    discovery = request_json(ISSUER + "/.well-known/openid-configuration")
    if discovery.get("issuer") != ISSUER:
        raise ValueError("예상하지 않은 인증 발급자입니다.")
    key = jwt.PyJWKClient(discovery["jwks_uri"]).get_signing_key_from_jwt(token)
    claims = jwt.decode(token, key.key, algorithms=["RS256"], audience=client_id, issuer=ISSUER,
                        options={"verify_iat": False})
    clock_difference = int(claims.get("iat", 0) - time.time())
    if clock_difference > 300:
        raise ValueError(f"인증서의 발급 시각이 현재 시각보다 {clock_difference}초 앞섭니다.")
    if claims.get("nonce") != nonce or not claims.get("sub"):
        raise ValueError("인증 응답 검증에 실패했습니다.")
    return claims


def login():
    previous = load_private()
    host_id = previous.get("ext_agent_host_id") or "urn:uuid:" + str(uuid.uuid4())
    if not previous:
        save_private({"ext_agent_host_id": host_id})
    verifier = secrets.token_urlsafe(64)
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
    callback = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            url = urllib.parse.urlparse(self.path)
            if url.path != CALLBACK_PATH:
                self.send_error(404)
                return
            params = urllib.parse.parse_qs(url.query)
            if params.get("state", [None])[0] != state:
                self.send_error(400, "OAuth state mismatch")
                return
            callback.update({key: values[0] for key, values in params.items() if values})
            body = "<h1>ChatGPT 인증 응답을 받았습니다</h1><p>이 창을 닫고 앱으로 돌아가세요.</p>".encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            pass  # Never log the authorization code or other callback parameters.

    with HTTPServer(("127.0.0.1", 0), Handler) as server:
        server.timeout = 1
        redirect_uri = f"http://127.0.0.1:{server.server_port}{CALLBACK_PATH}"
        client_id = previous.get("client_id") or "dynamic_agent_client"
        fields = {
            "client_id": client_id,
            "ext_agent_host_id": host_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": SCOPE,
            "resource": RESOURCE,
            "state": state,
            "nonce": nonce,
            "code_challenge_method": "S256",
            "code_challenge": challenge,
        }
        if client_id == "dynamic_agent_client":
            fields["agent_name_hint"] = APP_NAME
        url = ISSUER + "/api/accounts/authorize?" + urllib.parse.urlencode(fields)
        print("브라우저에서 다음 URL을 열고 ChatGPT 요금제 사용 동의를 확인하세요:", flush=True)
        print(url, flush=True)
        deadline = time.monotonic() + 300
        while not callback and time.monotonic() < deadline:
            server.handle_request()
    if not callback:
        raise TimeoutError("5분 동안 인증 응답을 받지 못했습니다.")
    if callback.get("error"):
        raise RuntimeError("ChatGPT 인증이 완료되지 않았습니다: " + callback["error"])
    issued_id = callback.get("client_id", previous.get("client_id"))
    if not issued_id or issued_id == "dynamic_agent_client":
        raise RuntimeError("발급된 OAuth client_id를 받지 못했습니다.")
    if previous.get("client_id") and issued_id != previous["client_id"]:
        raise RuntimeError("저장된 계정과 다른 OAuth 클라이언트가 반환됐습니다.")
    if not previous.get("client_id"):
        save_private({"ext_agent_host_id": host_id, "client_id": issued_id})
    token = exchange_token({
        "grant_type": "authorization_code",
        "client_id": issued_id,
        "code": callback["code"],
        "code_verifier": verifier,
        "redirect_uri": redirect_uri,
        "resource": RESOURCE,
    })
    claims = validate_id_token(token["id_token"], issued_id, nonce)
    if previous.get("subject") and claims["sub"] != previous["subject"]:
        raise RuntimeError("기존에 연결한 계정과 다른 ChatGPT 계정입니다.")
    scopes = token.get("scope", "").split()
    if "chatgpt.tokens.use.direct" not in scopes:
        raise RuntimeError("ChatGPT 요금제 이용량 공유 권한이 부여되지 않았습니다.")
    record = {
        "email": claims.get("email", ""),
        "issuer": ISSUER,
        "subject": claims["sub"],
        "client_id": issued_id,
        "ext_agent_host_id": host_id,
        "id_token": token["id_token"],
        "access_token": token["access_token"],
        "refresh_token": token["refresh_token"],
        "expires_in": int(token.get("expires_in", 3600)),
        "scopes": scopes,
        "saved_at": time.time(),
    }
    save_private(record)
    print("ChatGPT 요금제 이용량 공유 권한을 확인하고 자격 정보를 비공개 파일에 저장했습니다.")


def status():
    record = load_private()
    if not record:
        print("연결되지 않았습니다.")
        return
    print("연결 계정:", record.get("email") or "이메일 정보 없음")
    print("요금제 이용량 공유:", "허용" if "chatgpt.tokens.use.direct" in record.get("scopes", []) else "허용되지 않음")
    print("액세스 토큰 만료:", time.strftime("%Y-%m-%d %H:%M:%S %Z", time.localtime(record["saved_at"] + record["expires_in"])))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["login", "status"])
    args = parser.parse_args()
    try:
        if args.action == "login":
            login()
        else:
            status()
    except (KeyError, ValueError, RuntimeError, TimeoutError, urllib.error.URLError) as exc:
        print("연결 실패:", str(exc)[:160])
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
