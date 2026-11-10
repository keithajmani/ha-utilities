"""Tiny fake Home Assistant for testing ha.py: REST + WebSocket, in-memory state."""
import copy
import json
import sys
from datetime import datetime, timedelta
from aiohttp import web

TOKEN = "test-token"
DB = {
    "states": [
        {"entity_id": "media_player.kitchen_speaker", "state": "idle", "last_changed": "2026-10-25T23:00:00+00:00",
         "attributes": {"friendly_name": "Kitchen Speaker", "media_title": None}},
        {"entity_id": "media_player.office_speaker", "state": "playing", "last_changed": "2026-10-25T23:30:00+00:00",
         "attributes": {"friendly_name": "Office Speaker", "media_title": "Evening Jazz"}},
        {"entity_id": "switch.porch_light", "state": "off", "last_changed": "2026-10-25T22:00:00+00:00",
         "attributes": {"friendly_name": "Porch Light"}},
        {"entity_id": "automation.garage_door_open_alert", "state": "on", "last_changed": "2026-10-20T10:00:00+00:00",
         "attributes": {"friendly_name": "Garage door open alert", "id": "1700000000001"}},
        {"entity_id": "scene.movie_night", "state": "unknown", "last_changed": "2026-10-20T10:00:00+00:00",
         "attributes": {"friendly_name": "Movie night", "id": "1700000000101"}},
    ],
    "areas": [{"area_id": "kitchen", "name": "Kitchen"}, {"area_id": "office", "name": "Office"},
              {"area_id": "front_porch", "name": "Front Porch"}],
    "devices": [{"id": "dev1aaaaaaaa", "name": "Kitchen Speaker", "name_by_user": None, "area_id": "kitchen", "manufacturer": "Amazon", "model": "Speaker"},
                {"id": "dev2bbbbbbbb", "name": "Porch Lights", "name_by_user": None, "area_id": "front_porch", "manufacturer": "Lutron", "model": "Caseta"}],
    "entities": {
        "media_player.kitchen_speaker": {"entity_id": "media_player.kitchen_speaker", "device_id": "dev1aaaaaaaa", "area_id": None, "name": None, "original_name": "Kitchen Speaker", "platform": "alexa_devices", "icon": None, "disabled_by": None, "hidden_by": None, "modified_at": 1},
        "input_boolean.guest_mode": {"entity_id": "input_boolean.guest_mode", "unique_id": "guest_mode", "device_id": None, "area_id": None, "name": None, "original_name": "Guest mode", "platform": "input_boolean", "icon": None, "disabled_by": None, "hidden_by": None, "modified_at": 1},
        "input_number.bedtime_volume": {"entity_id": "input_number.bedtime_volume", "unique_id": "bedtime_volume", "device_id": None, "area_id": None, "name": None, "original_name": "Bedtime volume", "platform": "input_number", "icon": None, "disabled_by": None, "hidden_by": None, "modified_at": 1},
        "switch.porch_light": {"entity_id": "switch.porch_light", "device_id": "dev2bbbbbbbb", "area_id": "front_porch", "name": None, "original_name": "Porch Light", "platform": "lutron_caseta", "icon": None, "disabled_by": None, "hidden_by": None, "modified_at": 1},
    },
    "exposed": {"switch.porch_light": {"conversation": True, "cloud.alexa": False}},
    "entries": [{"entry_id": "e1", "domain": "alexa_media", "title": "Alexa Media Player", "state": "loaded", "disabled_by": None},
                {"entry_id": "e2", "domain": "homekit", "title": "Sensors Bridge", "state": "loaded", "disabled_by": None}, {"entry_id": "e3", "domain": "homekit_controller", "title": "Old Camera", "state": "not_loaded", "disabled_by": None, "source": "ignore"}, {"entry_id": "e4", "domain": "tplink", "title": "Patio Plug", "state": "setup_retry", "disabled_by": None, "source": "user", "reason": "no route"}],
    "lovelace": {"lovelace-media": {"views": [{"path": "music", "title": "Music", "cards": [{"type": "entities", "entities": ["media_player.kitchen_speaker"]}]}]}},
    "config": {
        "automation": {"1700000000001": {"id": "1700000000001", "alias": "Garage door open alert",
                                         "triggers": [{"trigger": "state", "entity_id": "cover.garage_door", "to": "open", "for": "00:10:00"}],
                                         "conditions": [{"condition": "state", "entity_id": "input_boolean.guest_mode", "state": "off"}],
                                         "actions": [{"alias": "Tell the kitchen", "action": "notify.send_message", "target": {"entity_id": "notify.kitchen_speaker"}}]}},
        "script": {},
        "scene": {"1700000000101": {"id": "1700000000101", "name": "Movie night", "entities": {"switch.porch_light": "off"}}},
    },
    "helpers": {
        "input_boolean": {"guest_mode": {"id": "guest_mode", "name": "Guest mode", "icon": "mdi:account"}},
        "input_number": {"bedtime_volume": {"id": "bedtime_volume", "name": "Bedtime volume", "min": 0, "max": 100, "step": 5, "mode": "slider"}},
    },
    "traces": {
        ("automation", "1700000000001"): [
            {"run_id": "r1", "state": "stopped", "script_execution": "failed_conditions", "last_step": "condition/0",
             "trigger": "state of cover.garage_door", "timestamp": {"start": "2026-11-08T22:00:00+00:00", "finish": "2026-11-08T22:00:00.1+00:00"},
             "trace": {"trigger/0": [{"path": "trigger/0", "timestamp": "2026-11-08T22:00:00+00:00",
                                      "changed_variables": {"trigger": {"description": "state of cover.garage_door"}}}],
                       "condition/0": [{"path": "condition/0", "timestamp": "2026-11-08T22:00:00+00:00", "result": {"result": False}}]}},
            {"run_id": "r2", "state": "stopped", "script_execution": "error", "last_step": "action/0", "error": "Action notify.send_message not found",
             "trigger": "state of cover.garage_door", "timestamp": {"start": "2026-11-09T01:00:00+00:00", "finish": "2026-11-09T01:00:01+00:00"},
             "trace": {"trigger/0": [{"path": "trigger/0", "timestamp": "2026-11-09T01:00:00+00:00",
                                      "changed_variables": {"trigger": {"description": "state of cover.garage_door"}}}],
                       "condition/0": [{"path": "condition/0", "timestamp": "2026-11-09T01:00:00+00:00", "result": {"result": True}}],
                       "action/0": [{"path": "action/0", "timestamp": "2026-11-09T01:00:01+00:00", "error": "Action notify.send_message not found",
                                     "result": {"params": {"domain": "notify", "service": "send_message"}}}]}},
        ],
    },
    "backup_cfg": {"create_backup": {"agent_ids": ["backup.local", "synology_dsm.nas"], "password": "SECRET-KEY", "include_database": True, "include_all_addons": False, "include_addons": ["core_mariadb"], "include_folders": []},
                   "retention": {"copies": 14, "days": None}, "schedule": {"recurrence": "daily", "time": "05:30:00", "days": []}},
    "calls": [],
}


def auth(req):
    if req.headers.get("Authorization") != f"Bearer {TOKEN}":
        raise web.HTTPUnauthorized()


async def states(req):
    auth(req)
    return web.json_response(DB["states"])


async def state_one(req):
    auth(req)
    for s in DB["states"]:
        if s["entity_id"] == req.match_info["eid"]:
            return web.json_response(s)
    raise web.HTTPNotFound()


HISTORY = [("off", "2026-10-25T20:00:00+00:00"), ("on", "2026-10-25T21:00:00+00:00"),
           ("off", "2026-10-25T21:05:00+00:00"), ("on", "2026-10-27T12:00:00+00:00")]


async def history(req):
    """Like HA: the window ends one day after the start unless end_time is given."""
    auth(req)
    eids = req.query["filter_entity_id"].split(",")
    start = datetime.fromisoformat(req.match_info["start"])
    end = datetime.fromisoformat(req.query["end_time"]) if "end_time" in req.query else start + timedelta(days=1)
    rows = [{"state": st, "last_changed": ts} for st, ts in HISTORY if start <= datetime.fromisoformat(ts) <= end]
    return web.json_response([[dict(rows[0], entity_id=e)] + rows[1:] for e in eids] if rows else [])


async def template(req):
    auth(req)
    body = await req.json()
    return web.Response(text=f"rendered:{body['template']}")


async def services(req):
    auth(req)
    DB["calls"].append([req.match_info["domain"], req.match_info["service"], await req.json()])
    return web.json_response([])


async def config_cfg(req):
    auth(req)
    kind, cid = req.match_info["kind"], req.match_info["cid"]
    store = DB["config"][kind]
    if req.method == "GET":
        if cid not in store:
            raise web.HTTPNotFound()
        return web.json_response(store[cid])
    if req.method == "DELETE":
        store.pop(cid, None)
        return web.json_response({"result": "ok"})
    body = await req.json()
    store[cid] = {"id": cid, **{k: v for k, v in body.items() if k != "id"}} if kind != "script" else body
    return web.json_response({"result": "ok"})


def helper_ws(domain, action, msg):
    """Like HA's helper collections: update replaces the whole config; create makes the id from the name."""
    store = DB["helpers"].setdefault(domain, {})
    fields = {k: v for k, v in msg.items() if k not in ("id", "type", f"{domain}_id")}
    if action == "list":
        return list(store.values())
    if action == "create":
        iid = fields["name"].lower().replace(" ", "_")
        store[iid] = {"id": iid, **fields}
        DB["entities"][f"{domain}.{iid}"] = {"entity_id": f"{domain}.{iid}", "unique_id": iid, "platform": domain, "device_id": None,
                                            "area_id": None, "name": None, "original_name": fields["name"], "icon": None,
                                            "disabled_by": None, "hidden_by": None, "modified_at": 1}
        return store[iid]
    iid = msg[f"{domain}_id"]
    if iid not in store:
        raise KeyError("not_found")
    if action == "update":
        store[iid] = {"id": iid, **fields}
        return store[iid]
    if action == "delete":
        del store[iid]
        DB["entities"] = {k: v for k, v in DB["entities"].items() if not (v.get("platform") == domain and v.get("unique_id") == iid)}
        return None
    raise KeyError("unknown_command")


async def diag(req):
    auth(req)
    return web.json_response({"options": {"mode": "bridge", "filter": {"include_domains": [], "include_entities": ["binary_sensor.a", "binary_sensor.b"]}},
                              "accessories": [{"aid": 1}, {"aid": 2}], "data": {"x": 1}})


def ws_handle(msg):
    t = msg["type"]
    if t.split("/")[0] in ("input_boolean", "input_number", "input_select", "input_text", "input_datetime",
                           "input_button", "counter", "timer", "schedule") and t.count("/") == 1:
        return helper_ws(*t.split("/"), msg)
    if t == "trace/list":
        return [{k: v for k, v in r.items() if k != "trace"} for r in DB["traces"].get((msg["domain"], msg["item_id"]), [])]
    if t == "trace/get":
        run = next(r for r in DB["traces"].get((msg["domain"], msg["item_id"]), []) if r["run_id"] == msg["run_id"])
        return dict(run, config=DB["config"][msg["domain"]][msg["item_id"]])
    if t == "config/area_registry/list":
        return DB["areas"]
    if t == "config/device_registry/list":
        return DB["devices"]
    if t == "config/device_registry/update":
        d = next(d for d in DB["devices"] if d["id"] == msg["device_id"])
        d.update({k: v for k, v in msg.items() if k in ("name_by_user", "area_id")})
        return d
    if t == "config/entity_registry/list":
        return list(DB["entities"].values())
    if t == "config/entity_registry/get":
        if msg["entity_id"] not in DB["entities"]:
            raise KeyError("not_found")
        return DB["entities"][msg["entity_id"]]
    if t == "config/entity_registry/update":
        e = DB["entities"][msg["entity_id"]]
        e.update({k: v for k, v in msg.items() if k in ("name", "area_id", "icon", "disabled_by", "hidden_by")})
        e["modified_at"] += 1
        return {"entity_entry": e}
    if t == "homeassistant/expose_entity/list":
        return {"exposed_entities": DB["exposed"]}
    if t == "homeassistant/expose_entity":
        for eid in msg["entity_ids"]:
            for a in msg["assistants"]:
                DB["exposed"].setdefault(eid, {})[a] = msg["should_expose"]
        return None
    if t == "repairs/list_issues":
        return {"issues": [{"domain": "spook", "issue_id": "homekit_unknown_entity_references", "severity": "warning", "translation_key": "x", "created": "2026-10-20T10:00:00+00:00", "ignored": False}]}
    if t == "system_log/list":
        return [{"name": "custom_components.icloud3", "message": ["KeyError 'gps'"], "level": "ERROR", "count": 299, "timestamp": 1761436800.0}]
    if t == "config_entries/get":
        return [e for e in DB["entries"] if not msg.get("domain") or e["domain"] == msg["domain"]]
    if t == "config_entries/disable":
        e = next(e for e in DB["entries"] if e["entry_id"] == msg["entry_id"])
        e["disabled_by"] = msg["disabled_by"]
        e["state"] = "not_loaded" if msg["disabled_by"] else "loaded"
        return {"require_restart": False}
    if t == "lovelace/dashboards/list":
        return [{"url_path": k, "title": k, "mode": "storage"} for k in DB["lovelace"]] + [{"url_path": "dashboard-generated", "title": "Generated Dashboard", "mode": "storage"}]
    if t == "lovelace/config":
        return copy.deepcopy(DB["lovelace"].get(msg.get("url_path") or "lovelace", {"views": []}))
    if t == "lovelace/config/save":
        DB["lovelace"][msg.get("url_path") or "lovelace"] = msg["config"]
        return None
    if t == "backup/info":
        return {"backups": [{"backup_id": "abc123", "name": "Automatic backup 2026.10.4", "date": "2026-10-25T09:30:00+00:00", "with_automatic_settings": True,
                             "agents": {"synology_dsm.nas": {"size": 2600000000, "protected": True}, "cloud.cloud": {"size": 2600000000, "protected": True}}}],
                "last_completed_automatic_backup": "2026-10-25T09:31:00+00:00", "next_automatic_backup": "2026-10-26T09:30:00+00:00"}
    if t == "backup/config/info":
        return {"config": copy.deepcopy(DB["backup_cfg"])}
    if t == "backup/config/update":
        for k in ("retention", "schedule"):
            if k in msg:
                DB["backup_cfg"][k].update(msg[k])
        if "create_backup" in msg:
            DB["backup_cfg"]["create_backup"].update(msg["create_backup"])
        return None
    if t == "recorder/list_statistic_ids":
        return [{"statistic_id": "sensor.laundry_temperature", "name": "Laundry Temperature", "statistics_unit_of_measurement": "°C"},
                {"statistic_id": "sensor.porch_energy", "name": "Porch Energy", "statistics_unit_of_measurement": "kWh"}]
    if t == "recorder/statistics_during_period":
        pts = [{"start": 1761436800000, "mean": 20.5, "min": 19.8, "max": 21.4},
               {"start": "2026-10-26T01:00:00+00:00", "mean": 22.25, "min": 21.0, "max": 24.0}]
        return {sid: pts for sid in msg["statistic_ids"] if sid == "sensor.laundry_temperature"}
    raise KeyError("unknown_command")


async def websocket(req):
    ws = web.WebSocketResponse()
    await ws.prepare(req)
    await ws.send_json({"type": "auth_required"})
    m = await ws.receive_json()
    if m.get("access_token") != TOKEN:
        await ws.send_json({"type": "auth_invalid"})
        return ws
    await ws.send_json({"type": "auth_ok"})
    async for raw in ws:
        msg = json.loads(raw.data)
        try:
            res = ws_handle(msg)
            await ws.send_json({"id": msg["id"], "type": "result", "success": True, "result": res})
        except KeyError as e:
            await ws.send_json({"id": msg["id"], "type": "result", "success": False, "error": {"code": str(e).strip("'"), "message": "mock"}})
    return ws


app = web.Application()
app.add_routes([
    web.get("/api/states", states), web.get("/api/states/{eid}", state_one),
    web.get("/api/history/period/{start}", history), web.post("/api/template", template),
    web.post("/api/services/{domain}/{service}", services),
    web.route("*", "/api/config/{kind}/config/{cid}", config_cfg),
    web.get("/api/diagnostics/config_entry/{eid}", diag),
    web.get("/api/websocket", websocket),
])

if __name__ == "__main__":
    web.run_app(app, port=int(sys.argv[1]), print=None)
