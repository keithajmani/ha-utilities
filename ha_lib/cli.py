"""Argument parsing and dispatch."""
import argparse
import importlib
import pkgutil
import sys
from types import SimpleNamespace

from . import __version__, commands
from .client import HA
from .config import HAError, load
from .output import Out
from .registry import COMMANDS
from .safety import audit


def _load_commands():
    for m in pkgutil.iter_modules(commands.__path__):
        importlib.import_module(f"{commands.__name__}.{m.name}")


def _common(write):
    p = argparse.ArgumentParser(add_help=False)
    g = p.add_argument_group("output")
    g.add_argument("--json", action="store_true", help="compact JSON output")
    g.add_argument("--all", action="store_true", help="show every row")
    g.add_argument("--limit", type=int, help="max rows")
    if write:
        w = p.add_argument_group("write safety")
        w.add_argument("--yes", action="store_true", help="apply (needs --plan from the dry run)")
        w.add_argument("--plan", dest="plan_id", help="plan id printed by the dry run")
    return p


def build_parser():
    _load_commands()
    root = argparse.ArgumentParser(prog="ha.py", description="Home Assistant reads and safe writes. Writes are a dry run unless --yes --plan <id>.")
    root.add_argument("--version", action="version", version=f"ha.py {__version__}")
    subs = {(): root.add_subparsers(dest="cmd0", metavar="command")}
    for name in sorted(COMMANDS):
        spec = COMMANDS[name]
        for depth in range(1, len(name)):
            prefix = name[:depth]
            if prefix not in subs:
                grp = subs[prefix[:-1]].add_parser(prefix[-1], help=f"{prefix[-1]} commands")
                subs[prefix] = grp.add_subparsers(dest=f"cmd{depth}", metavar="subcommand")
        tag = "[write] " if spec["write"] else ""
        p = subs[name[:-1]].add_parser(name[-1], help=tag + spec["help"], description=tag + spec["help"],
                                       parents=[_common(spec["write"])])
        if spec["fn"].args:
            spec["fn"].args(p)
        p.set_defaults(_spec=spec)
    return root


def main(argv):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "_spec"):
        parser.print_help()
        return 2
    ctx = None
    try:
        s = load()
        out = Out(s, as_json=args.json, limit=args.limit, show_all=args.all)
        canon = [a for i, a in enumerate(argv) if a != "--yes" and a != "--plan" and not (i and argv[i - 1] == "--plan")
                 and not a.startswith("--plan=")]
        ctx = SimpleNamespace(s=s, out=out, ha=HA(s), args=args, argv=canon,
                              yes=getattr(args, "yes", False), plan_id=getattr(args, "plan_id", None))
        rc = args._spec["fn"](ctx)
        if not args._spec["write"]:
            audit(ctx, "read")
        return rc or 0
    except HAError as e:
        print(f"error: {e}" + (f" · {e.hint}" if e.hint else ""), file=sys.stderr)
        if ctx and not args._spec["write"]:
            audit(ctx, "error", error=str(e))
        return e.code
    except KeyboardInterrupt:
        return 130
    finally:
        if ctx:
            ctx.ha.close()
