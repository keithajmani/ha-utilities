"""Command registry. Each command module registers itself with @command; cli.py builds the parser from it.

Add a command:
    @command("thing get", "one-line help", write=False)
    def thing_get(ctx): ...
    thing_get.args = lambda p: p.add_argument("target")

Add a restorer for a write's snapshot kind:
    @restorer("thing")
    def restore_thing(ctx, before) -> Plan: ...
"""

COMMANDS = {}
RESTORERS = {}


def command(name, help, write=False):
    def deco(fn):
        COMMANDS[tuple(name.split())] = {"fn": fn, "help": help, "write": write}
        fn.args = getattr(fn, "args", None)
        return fn
    return deco


def restorer(kind):
    def deco(fn):
        RESTORERS[kind] = fn
        return fn
    return deco
