"""Service calls. Always a write: an announcement or a toggle is a real-world action."""
import json

from ..config import HAError
from ..registry import command
from ..safety import Change, Plan, run


@command("call", "call a service, e.g. notify.send_message (no automatic undo)", write=True)
def call(ctx):
    a = ctx.args
    if "." not in a.service:
        raise HAError(f"bad service {a.service!r}", "use domain.service", 2)
    domain, service = a.service.split(".", 1)
    try:
        data = json.loads(a.data) if a.data else {}
    except json.JSONDecodeError as e:
        raise HAError("--data is not valid JSON", str(e), 2)
    if a.entity:
        data["entity_id"] = a.entity if len(a.entity) > 1 else a.entity[0]
    params = {"return_response": ""} if a.response else None

    def apply():
        res = ctx.ha.post(f"/api/services/{domain}/{service}", body=data, params=params)
        if a.response and res is not None:
            ctx.out.obj(res.get("service_response", res) if isinstance(res, dict) else res, name=f"{a.service}-response")

    return run(ctx, Plan(title="service call", changes=[Change(a.service, "data", None, data)], apply=apply,
                         name="call", rollback="none automatic: undo by calling the opposite service if there is one"))


def _call_args(p):
    p.add_argument("service", help="domain.service")
    p.add_argument("--entity", nargs="+", help="target entity ids")
    p.add_argument("--data", help="JSON service data")
    p.add_argument("--response", action="store_true", help="ask for and print the service response")


call.args = _call_args
