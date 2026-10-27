"""HA transport: REST over urllib, WebSocket over the websockets library. Login is done once per run."""
import json
import urllib.error
import urllib.parse
import urllib.request

from .config import HAError


class HA:
    def __init__(self, settings, timeout=30):
        self.s = settings
        self.timeout = timeout
        self._ws = None
        self._id = 0

    # ---- REST ----
    def rest(self, method, path, body=None, params=None, raw=False):
        url = self.s.url + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {self.s.token}")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                text = r.read().decode()
        except urllib.error.HTTPError as e:
            detail = e.read().decode()[:200].strip()
            if e.code == 401:
                raise HAError("401 token rejected", f"check {self.s.home}/token")
            if e.code == 404:
                raise HAError(f"404 not found: {path}", detail or None)
            raise HAError(f"HTTP {e.code} on {method} {path}", detail or None)
        except urllib.error.URLError as e:
            raise HAError(f"cannot reach HA at {self.s.url}", str(e.reason))
        if raw:
            return text
        return json.loads(text) if text else None

    def get(self, path, params=None):
        return self.rest("GET", path, params=params)

    def post(self, path, body=None, params=None):
        return self.rest("POST", path, body=body, params=params)

    # ---- WebSocket ----
    def _connect(self):
        try:
            from websockets.sync.client import connect
        except ImportError:
            raise HAError("websockets library missing", f"run: {self.s.home}/.venv/bin/pip install -r {self.s.home}/requirements.txt")
        ws_url = self.s.url.replace("https://", "wss://").replace("http://", "ws://") + "/api/websocket"
        try:
            ws = connect(ws_url, open_timeout=self.timeout, max_size=None)
        except OSError as e:
            raise HAError(f"cannot reach HA WebSocket at {ws_url}", str(e))
        hello = json.loads(ws.recv(timeout=self.timeout))
        if hello.get("type") != "auth_required":
            raise HAError("unexpected WebSocket greeting", str(hello)[:200])
        ws.send(json.dumps({"type": "auth", "access_token": self.s.token}))
        res = json.loads(ws.recv(timeout=self.timeout))
        if res.get("type") != "auth_ok":
            raise HAError("401 token rejected (WebSocket)", f"check {self.s.home}/token")
        self._ws = ws

    def ws(self, type_, **payload):
        if self._ws is None:
            self._connect()
        self._id += 1
        msg = {"id": self._id, "type": type_, **payload}
        self._ws.send(json.dumps(msg))
        while True:
            res = json.loads(self._ws.recv(timeout=self.timeout))
            if res.get("id") == self._id and res.get("type") == "result":
                break
        if not res.get("success"):
            err = res.get("error") or {}
            raise HAError(f"{type_} failed: {err.get('code', '?')}", err.get("message"))
        return res.get("result")

    def close(self):
        if self._ws is not None:
            self._ws.close()
            self._ws = None

    # ---- lookups shared by commands ----
    def areas(self):
        return self.ws("config/area_registry/list")

    def resolve_area(self, value):
        """Area id from an id or a name. 'none' means clear (use the device's area)."""
        if value is None:
            return None
        if value.lower() in ("none", "device", ""):
            return None
        for a in self.areas():
            if value in (a["area_id"], a["name"]) or value.lower() == a["name"].lower():
                return a["area_id"]
        raise HAError(f"no area named {value!r}", "list them with: ha.py areas")
