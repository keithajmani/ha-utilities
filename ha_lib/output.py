"""Compact output, redaction, local times and big-result spill to files."""
import json
import os
import sys
from datetime import datetime, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

REDACTED = "«redacted»"


class Out:
    def __init__(self, settings, as_json=False, limit=None, show_all=False):
        self.s = settings
        self.as_json = as_json
        self.limit = None if show_all else (limit or settings.max_rows)
        self.tz = ZoneInfo(settings.timezone) if (ZoneInfo and settings.timezone) else None  # None = local

    # ---- redaction ----
    def redact(self, obj):
        if isinstance(obj, dict):
            return {k: (REDACTED if self._secret(k) and v not in (None, "", False) else self.redact(v)) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self.redact(v) for v in obj]
        return obj

    def _secret(self, key):
        k = str(key).lower()
        return any(r in k for r in self.s.redact_keys)

    # ---- time ----
    def time(self, value, fmt="%b %d %H:%M"):
        """ISO string or epoch to a short local time."""
        if value in (None, ""):
            return "-"
        if isinstance(value, (int, float)):
            dt = datetime.fromtimestamp(value, timezone.utc)
        else:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(self.tz).strftime(fmt)

    def now_stamp(self):
        return datetime.now(self.tz).strftime("%Y-%m-%dT%H-%M-%S")

    # ---- emit ----
    def rows(self, rows, cols, total=None, note=None):
        """rows: list of dicts. cols: keys to show; the first column is padded."""
        rows = [self.redact(r) for r in rows]
        total = len(rows) if total is None else total
        shown = rows if self.limit is None else rows[: self.limit]
        if self.as_json:
            print(json.dumps([{c: r.get(c) for c in cols if r.get(c) not in (None, "")} for r in shown], separators=(",", ":"), default=str, ensure_ascii=False))
        else:
            # First two columns are padded and unlabelled; the rest print as key=value when set.
            lead = cols[:2]
            widths = {c: min(max([len(_cell(r.get(c), quote=False)) for r in shown] + [0]), 48) for c in lead}
            for r in shown:
                parts = [_cell(r.get(c), quote=False).ljust(widths[c]) for c in lead]
                parts += [f"{c}={_cell(r[c])}" for c in cols[2:] if r.get(c) not in (None, "", [], {})]
                print("  ".join(parts).rstrip())
        if len(shown) < total:
            self.note(f"{len(shown)} of {total} shown · --all for all")
        elif not shown:
            self.note("nothing matched")
        if note:
            self.note(note)

    def obj(self, obj, name="result"):
        """Print an object compactly, or spill it to a file when big."""
        obj = self.redact(obj)
        text = json.dumps(obj, separators=(",", ":"), default=str, ensure_ascii=False)
        if len(text) <= self.s.big_output_bytes:
            print(text)
            return None
        path = self.save(name, obj)
        print(f"saved {len(text):,} bytes to {path}")
        print("summary: " + _summary(obj))
        return path

    def save(self, name, obj, folder="out"):
        d = self.s.path(folder)
        os.makedirs(d, exist_ok=True)
        base = os.path.join(d, f"{self.now_stamp()}_{_safe(name)}")
        path, n = base + ".json", 2
        while os.path.exists(path):  # two saves in the same second
            path, n = f"{base}-{n}.json", n + 1
        with open(path, "w") as f:
            json.dump(obj, f, indent=2, default=str)
            f.write("\n")
        return path

    def line(self, text):
        print(text)

    def note(self, text):
        print(text, file=sys.stderr)


def _cell(v, quote=True):
    if v is None:
        return "-"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, (list, dict)):
        return json.dumps(v, separators=(",", ":"), default=str)
    s = str(v).replace("\n", " ")
    return f'"{s}"' if quote and " " in s and len(s) < 80 else s[:120]


def _safe(name):
    return "".join(c if c.isalnum() or c in "-_." else "-" for c in name)[:60]


def _summary(obj, depth=0):
    if isinstance(obj, dict):
        parts = []
        for k, v in list(obj.items())[:12]:
            if isinstance(v, list):
                parts.append(f"{k}[{len(v)}]")
            elif isinstance(v, dict):
                parts.append(f"{k}{{{len(v)}}}")
            else:
                parts.append(k)
        more = f" +{len(obj) - 12} more" if len(obj) > 12 else ""
        return "{" + ", ".join(parts) + more + "}"
    if isinstance(obj, list):
        return f"list of {len(obj)}"
    return type(obj).__name__
