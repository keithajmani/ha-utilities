"""Settings: home folder, token, url and ha.toml."""
import os
from dataclasses import dataclass, field

try:
    import tomllib
except ImportError:  # Python < 3.11
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None

DEFAULTS = {
    "timezone": "",  # empty = this computer's local time zone
    "big_output_bytes": 4000,
    "redact_keys": ["password", "token", "access_token", "refresh_token", "api_key", "encryption_key", "secret"],
    "protected_dashboards": [],
    "fields": {},
    "max_rows": 50,
}


class HAError(Exception):
    """An error shown to the user as one line, with a hint."""

    def __init__(self, msg, hint=None, code=1):
        super().__init__(msg)
        self.hint = hint
        self.code = code


@dataclass
class Settings:
    home: str
    url: str
    token: str = field(repr=False)
    timezone: str
    big_output_bytes: int
    redact_keys: list
    protected_dashboards: list
    fields: dict
    max_rows: int

    def path(self, *parts):
        return os.path.join(self.home, *parts)


def _read(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except FileNotFoundError:
        return None


def default_home():
    """$HA_HOME, else the ha.py folder if it holds a `url` file, else ~/.config/ha-utilities."""
    if os.environ.get("HA_HOME"):
        return os.path.expanduser(os.environ["HA_HOME"])
    code_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if os.path.exists(os.path.join(code_dir, "url")):
        return code_dir
    return os.path.expanduser("~/.config/ha-utilities")


def load(home=None):
    home = home or default_home()
    opts = dict(DEFAULTS)
    toml_path = os.path.join(home, "ha.toml")
    if os.path.exists(toml_path):
        if tomllib is None:  # never ignore settings silently: they include protected dashboards
            raise HAError("cannot read ha.toml on this Python", "install tomli in the venv: .venv/bin/pip install -r requirements.txt")
        with open(toml_path, "rb") as f:
            try:
                opts.update(tomllib.load(f))
            except tomllib.TOMLDecodeError as e:
                raise HAError("ha.toml has a syntax error", str(e))
    url = os.environ.get("HA_URL") or _read(os.path.join(home, "url"))
    token = os.environ.get("HA_TOKEN") or _read(os.path.join(home, "token"))
    if not url:
        raise HAError("no HA url", f"put it in {home}/url (e.g. http://homeassistant.local:8123) or set HA_URL")
    if not token:
        raise HAError("no HA token", f"put a long-lived access token in {home}/token or set HA_TOKEN")
    return Settings(
        home=home,
        url=url.rstrip("/"),
        token=token,
        timezone=opts["timezone"],
        big_output_bytes=int(opts["big_output_bytes"]),
        redact_keys=[k.lower() for k in opts["redact_keys"]],
        protected_dashboards=list(opts["protected_dashboards"]),
        fields=dict(opts["fields"]),
        max_rows=int(opts["max_rows"]),
    )
