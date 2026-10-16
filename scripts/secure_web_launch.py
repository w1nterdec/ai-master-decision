#!/usr/bin/env python3
"""Phase 5.0｜带登录鉴权的安全 Web 启动器（**不改动任何业务代码**）。

背景
----
沙箱的「发布为应用」只提供 HTTPS 分享链接，实测**不提供访问控制**（匿名即可
HTTP 200），且平台边缘代理会**剥离 Authorization 请求头**（实测：带 Basic 凭据
访问公网链接仍返回 401，而 realm 是本服务的，说明头未到达）。因此不能依赖
Basic Auth，改由应用层自己做**表单登录 + Cookie 会话**：

    手机浏览器 --HTTPS(平台)--> [本代理 :3000, 登录/Cookie] --HTTP/WS--> Streamlit :8502

设计要点
--------
* Streamlit 只绑 127.0.0.1:8502，对外不可达；对外端口只有本代理。
* 未认证：返回**登录页**（HTML 表单，适配手机），不是 401（避免手机弹系统认证框、
  且 Authorization 头会被平台剥离导致 Basic 根本不可用）。
* 认证通过后签发随机 session token，写入 HttpOnly Cookie；Cookie 与登录页走标准
  HTTP 语义，不依赖任何可能被边缘代理改写的头部。
* 采用**原始字节双向转发**，WebSocket（Streamlit 真实端点 /_stcore/stream）透传，
  交互可用；WebSocket 握手未认证时才返回 401（浏览器不会因此弹窗）。
* 口令比对用 hmac.compare_digest（常量时间）；失败次数按来源 IP 递增延时，
  缓解暴力破解。
* 凭据走环境变量 AUTH_USER / AUTH_PASS，**缺省时拒绝启动**（避免无鉴权上线）。
* 本文件是**新增的独立基础设施**，不 import、不修改 app.py 或 decision_system
  下任何模块，也不触碰数据库与决策逻辑。

用法（发布平台调用）
--------------------
    python3 scripts/secure_web_launch.py
环境变量
--------
    AUTH_USER / AUTH_PASS  必填；缺省时拒绝启动
    STREAMLIT_PORT         默认 8502（仅回环）
    PROXY_PORT             默认 3000（对外，平台把 HTTPS 映射到该端口）
    DECISION_DB_PATH       传给 Streamlit 的数据库路径
    SESSION_TTL            会话有效期（秒），默认 7 天
"""

from __future__ import annotations

import base64
import hmac
import html
import os
import secrets
import socket
import socketserver
import subprocess
import sys
import threading
import time
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

AUTH_USER = os.environ.get("AUTH_USER", "")
AUTH_PASS = os.environ.get("AUTH_PASS", "")
STREAMLIT_PORT = int(os.environ.get("STREAMLIT_PORT", "8502"))
PROXY_PORT = int(os.environ.get("PROXY_PORT", "3000"))
DB_PATH = os.environ.get("DECISION_DB_PATH", "data/decision.db")
SESSION_TTL = int(os.environ.get("SESSION_TTL", str(7 * 24 * 3600)))

BASIC_EXPECTED = f"{AUTH_USER}:{AUTH_PASS}".encode()
COOKIE_NAME = "aid_session"
LOGIN_PATH = "/__login"
LOGOUT_PATH = "/__logout"

_LOCK = threading.Lock()
_SESSIONS: dict[str, float] = {}   # token -> 过期时间戳
_FAILS: dict[str, int] = {}        # 来源 IP -> 连续失败次数


def _log(msg: str) -> None:
    print(f"[secure-web] {msg}", flush=True)


# ---------------------------------------------------------------------------
# 会话
# ---------------------------------------------------------------------------
def _issue_session() -> str:
    tok = secrets.token_urlsafe(32)
    with _LOCK:
        now = time.time()
        for k, exp in list(_SESSIONS.items()):
            if exp < now:
                _SESSIONS.pop(k, None)
        _SESSIONS[tok] = now + SESSION_TTL
    return tok


def _session_valid(tok: str | None) -> bool:
    if not tok:
        return False
    with _LOCK:
        exp = _SESSIONS.get(tok)
        if exp is None:
            return False
        if exp < time.time():
            _SESSIONS.pop(tok, None)
            return False
        return True


def _revoke(tok: str | None) -> None:
    if tok:
        with _LOCK:
            _SESSIONS.pop(tok, None)


# ---------------------------------------------------------------------------
# 上游 Streamlit（仅回环）
# ---------------------------------------------------------------------------
def start_streamlit() -> None:
    cmd = [
        sys.executable, "-m", "streamlit", "run", "app.py",
        "--server.port", str(STREAMLIT_PORT),
        "--server.address", "127.0.0.1",
        "--server.headless", "true",
        "--browser.gatherUsageStats", "false",
    ]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    env["DECISION_DB_PATH"] = DB_PATH
    subprocess.Popen(cmd, cwd=str(ROOT), env=env)
    for i in range(60):
        try:
            with socket.create_connection(("127.0.0.1", STREAMLIT_PORT), timeout=1):
                _log(f"Streamlit 已就绪 127.0.0.1:{STREAMLIT_PORT}（{i}s）")
                return
        except OSError:
            time.sleep(1)
    _log("警告：Streamlit 未在 60s 内就绪，代理仍将启动")


# ---------------------------------------------------------------------------
# HTTP 解析
# ---------------------------------------------------------------------------
def _read_head(conn: socket.socket) -> tuple[bytes, dict[bytes, bytes], bytes] | None:
    buf = b""
    while b"\r\n\r\n" not in buf:
        try:
            chunk = conn.recv(65536)
        except OSError:
            return None
        if not chunk:
            return None
        buf += chunk
        if len(buf) > 1 << 20:
            return None
    head, _, rest = buf.partition(b"\r\n\r\n")
    headers: dict[bytes, bytes] = {}
    for line in head.split(b"\r\n")[1:]:
        k, _, v = line.partition(b":")
        if k:
            headers[k.strip().lower()] = v.strip()
    return head, headers, rest


def _basic_ok(headers: dict[bytes, bytes]) -> bool:
    raw = headers.get(b"authorization")
    if not raw:
        return False
    parts = raw.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != b"basic":
        return False
    try:
        decoded = base64.b64decode(parts[1])
    except Exception:  # noqa: BLE001
        return False
    return hmac.compare_digest(decoded, BASIC_EXPECTED)


def _cookie_token(headers: dict[bytes, bytes]) -> str | None:
    raw = headers.get(b"cookie")
    if not raw:
        return None
    for part in raw.decode("latin-1").split(";"):
        k, _, v = part.strip().partition("=")
        if k.strip() == COOKIE_NAME:
            return v.strip()
    return None


def _authorized(headers: dict[bytes, bytes], query: dict[str, list[str]]) -> bool:
    """Basic Auth（若头部存活）或 Cookie / ?token= 会话，任一通过即可。"""
    if _basic_ok(headers):
        return True
    tok = _cookie_token(headers)
    if tok is None:
        vals = query.get("token") or []
        tok = vals[0] if vals else None
    return _session_valid(tok)


def _normalize_host(head: bytes, headers: dict[bytes, bytes]) -> bytes:
    """把 Host 归一为 Origin 的 netloc。

    发布平台会把对外请求的 Host 头改写成内部域名
    （实测：Host=3000-<id>.e2b.gz3.sandbox.cloudstudio.club），而 Origin 仍是公网
    域名。Streamlit 的 WebSocket 端点会校验两者一致，不一致就拒绝
    （"Rejecting WebSocket connection with disallowed Origin or Host header"），
    导致前端无限重连、页面停在骨架。因此在这里按 Origin 重写 Host。
    """
    origin = headers.get(b"origin")
    if not origin:
        return head
    try:
        netloc = origin.decode("latin-1").split("://", 1)[1].split("/", 1)[0]
    except (IndexError, UnicodeDecodeError):
        return head
    if not netloc:
        return head
    lines = head.split(b"\r\n")
    replaced = False
    for i, line in enumerate(lines):
        if line.lower().startswith(b"host:"):
            lines[i] = b"Host: " + netloc.encode("latin-1")
            replaced = True
            break
    if not replaced:
        return head
    return b"\r\n".join(lines)


def _pump(src: socket.socket, dst: socket.socket) -> None:
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    finally:
        try:
            dst.shutdown(socket.SHUT_WR)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# 登录页
# ---------------------------------------------------------------------------
def _login_page(error: str = "") -> bytes:
    err = (
        f'<div class="err">{html.escape(error)}</div>' if error else ""
    )
    page = f"""<!doctype html>
<html lang="zh-CN"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="robots" content="noindex,nofollow">
<title>登录 · AI 硕士动态择校系统</title>
<style>
*{{box-sizing:border-box}}
body{{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
background:#0f172a;color:#e2e8f0;font:16px/1.6 -apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;padding:24px}}
.card{{width:100%;max-width:360px;background:#1e293b;border:1px solid #334155;border-radius:14px;padding:28px 24px}}
h1{{margin:0 0 6px;font-size:19px;color:#f8fafc}}
p.sub{{margin:0 0 20px;font-size:13px;color:#94a3b8}}
label{{display:block;font-size:13px;color:#cbd5e1;margin:14px 0 6px}}
input{{width:100%;padding:12px 12px;font-size:16px;border-radius:9px;border:1px solid #475569;
background:#0f172a;color:#f1f5f9;outline:none}}
input:focus{{border-color:#38bdf8}}
button{{margin-top:22px;width:100%;padding:13px;font-size:16px;font-weight:600;border:0;border-radius:9px;
background:#38bdf8;color:#05263b;cursor:pointer}}
.err{{margin-top:16px;padding:10px 12px;border-radius:8px;background:#7f1d1d;color:#fecaca;font-size:13px}}
.foot{{margin-top:18px;font-size:12px;color:#64748b;text-align:center}}
</style></head>
<body><div class="card">
<h1>2028 AI 硕士动态择校系统</h1>
<p class="sub">该页面含证据核验与权重修改等写入操作，需登录后访问。</p>
{err}
<form method="post" action="{LOGIN_PATH}" autocomplete="on">
<label for="u">用户名</label>
<input id="u" name="user" type="text" autocomplete="username" required autofocus>
<label for="p">密码</label>
<input id="p" name="pass" type="password" autocomplete="current-password" required>
<button type="submit">登 录</button>
</form>
<div class="foot">会话保留 7 天，可随时退出</div>
</div></body></html>"""
    return page.encode("utf-8")


def _send(conn: socket.socket, status: str, body: bytes,
          ctype: str = "text/html; charset=utf-8",
          extra: bytes = b"") -> None:
    conn.sendall(
        f"HTTP/1.1 {status}\r\n".encode()
        + b"Content-Type: " + ctype.encode() + b"\r\n"
        + b"Content-Length: " + str(len(body)).encode() + b"\r\n"
        + b"Cache-Control: no-store\r\n"
        + extra
        + b"Connection: close\r\n\r\n" + body
    )
    conn.close()


# ---------------------------------------------------------------------------
# 代理
# ---------------------------------------------------------------------------
class ProxyHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        conn = self.request
        peer = self.client_address[0] if self.client_address else "?"
        parsed = _read_head(conn)
        if parsed is None:
            conn.close()
            return
        head, headers, rest = parsed

        # 读满请求体
        try:
            need = int(headers.get(b"content-length", b"0")) - len(rest)
        except ValueError:
            need = 0
        body = rest
        while need > 0:
            chunk = conn.recv(min(65536, need))
            if not chunk:
                break
            body += chunk
            need -= len(chunk)

        try:
            line0 = head.split(b"\r\n")[0].decode("latin-1")
            method, target, _ = line0.split(" ", 2)
        except ValueError:
            conn.close()
            return
        path, _, qs = target.partition("?")
        query = urllib.parse.parse_qs(qs)

        # ---- 退出 ----
        if path == LOGOUT_PATH:
            _revoke(_cookie_token(headers))
            _send(conn, "303 See Other", b"",
                  extra=b"Location: /\r\n"
                        + f"Set-Cookie: {COOKIE_NAME}=; Path=/; Max-Age=0\r\n".encode())
            return

        # ---- 登录提交 ----
        if path == LOGIN_PATH and method.upper() == "POST":
            self._do_login(conn, peer, body)
            return

        # ---- 已认证：透传 ----
        if _authorized(headers, query):
            self._relay(conn, head, headers, body)
            return

        # ---- 未认证 ----
        # WebSocket 握手不重定向到登录页：直接 401，避免前端无限重试弹窗。
        if headers.get(b"upgrade", b"").lower() == b"websocket":
            _send(conn, "401 Unauthorized", b"")
            return
        _send(conn, "200 OK", _login_page())

    # ---------------------------
    def _do_login(self, conn: socket.socket, peer: str, body: bytes) -> None:
        with _LOCK:
            fails = _FAILS.get(peer, 0)
        if fails >= 3:
            time.sleep(min(2 ** (fails - 2), 30))

        form = urllib.parse.parse_qs(body.decode("utf-8", "replace"))
        user = (form.get("user") or [""])[0]
        pwd = (form.get("pass") or [""])[0]
        ok = hmac.compare_digest(user.encode(), AUTH_USER.encode()) and \
            hmac.compare_digest(pwd.encode(), AUTH_PASS.encode())
        if not ok:
            with _LOCK:
                _FAILS[peer] = _FAILS.get(peer, 0) + 1
            _log(f"登录失败 来源={peer} 累计={_FAILS[peer]}")
            _send(conn, "200 OK", _login_page("用户名或密码不正确"))
            return

        with _LOCK:
            _FAILS.pop(peer, None)
        tok = _issue_session()
        _log(f"登录成功 来源={peer}")
        cookie = (
            f"Set-Cookie: {COOKIE_NAME}={tok}; Path=/; Max-Age={SESSION_TTL}; "
            "HttpOnly; SameSite=Lax\r\n"
        ).encode()
        _send(conn, "303 See Other", b"", extra=b"Location: /\r\n" + cookie)

    # ---------------------------
    def _relay(self, conn: socket.socket, head: bytes,
               headers: dict[bytes, bytes], body: bytes) -> None:
        try:
            up = socket.create_connection(("127.0.0.1", STREAMLIT_PORT), timeout=60)
        except OSError:
            _send(conn, "502 Bad Gateway",
                  "<h1>502</h1><p>上游 Streamlit 未就绪</p>".encode("utf-8"))
            return
        up.sendall(_normalize_host(head, headers) + b"\r\n\r\n" + body)
        t1 = threading.Thread(target=_pump, args=(conn, up), daemon=True)
        t2 = threading.Thread(target=_pump, args=(up, conn), daemon=True)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        for s in (up, conn):
            try:
                s.close()
            except OSError:
                pass


class Proxy(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main() -> int:
    if not AUTH_USER or not AUTH_PASS:
        _log("拒绝启动：未设置 AUTH_USER / AUTH_PASS，不允许无鉴权对外暴露")
        return 1
    start_streamlit()
    srv = Proxy(("0.0.0.0", PROXY_PORT), ProxyHandler)
    _log(f"登录鉴权代理已启动 0.0.0.0:{PROXY_PORT} -> 127.0.0.1:{STREAMLIT_PORT}")
    _log(f"未认证访问将返回登录页；WebSocket 未认证返回 401")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
