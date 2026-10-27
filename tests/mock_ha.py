"""Tiny fake Home Assistant for testing ha.py: REST + WebSocket, in-memory state."""
import copy
import json
import sys
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
    ],
    "areas": [{"area_id": "kitchen", "name": "Kitchen"}, {"area_id": "office", "name": "Office"},
              {"area_id": "front_porch", "name": "Front Porch"}],
    "devices": [{"id": "dev1aaaaaaaa", "name": "Kitchen Speaker", "name_by_user": None, "area_id": "kitchen", "manufacturer": "Amazon", "model": "Speaker"},
                {"id": "dev2bbbbbbbb", "name": "Porch Lights", "name_by_user": None, "area_id": "front_porch", "manufacturer": "Lutron", "model": "Caseta"}],
    "entities": {
        "media_player.kitchen_speaker": {"entity_id": "media_player.kitchen_speaker", "device_id": "dev1aaaaaaaa", "area_id": None, "name": None, "original_name": "Kitchen Speaker", "platform": "alexa_devices", "icon": None, "disabled_by": None, "hidden_by": None, "modified_at": 1},
        "switch.porch_light": {"entity_id": "switch.porch_light", "device_id": "dev2bbbbbbbb", "area_id": "front_porch", "name": None, "original_name": "Porch Light", "platform": "lutron_caseta", "icon": None, "disabled_by": None, "hidden_by": None, "modified_at": 1},
    },
    "exposed": {"switch.porch_light": {"conversation": True, "cloud.alexa": False}},
    "entries": [{"entry_id": "e1", "domain": "alexa_media", "title": "Alexa Media Player", "state": "loaded", "disabled_by": None},
                {"entry_id": "e2", "domain": "homekit", "title": "Sensors Bridge", "state": "loaded", "disabled_by": None}, {"entry_id": "e3", "domain": "homekit_controller", "title": "Old Camera", "state": "not_loaded", "disabled_by": None, "source": "ignore"}, {"entry_id": "e4", "domain": "tplink", "title": "Patio Plug", "state": "setup_retry", "disabled_by": None, "source": "user", "reason": "no route"}],
    "lovelace": {"lovelace-media": {"views": [{"path": "music", "title": "Music", "cards": [{"type": "entities", "entities": ["media_player.kitchen_speaker"]}]}]}},
    "automations": {"1700000000001": {"id": "1700000000001", "alias": "Garage door open alert", "triggers": [], "actions": []}},
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


async def history(req):
    auth(req)
    eids = req.query["filter_entity_id"].split(",")
    return web.json_response([[{"entity_id": e, "state": "off", "last_changed": "2026-10-25T20:00:00+00:00"},
                               {"state": "on", "last_changed": "2026-10-25T21:00:00+00:00"},
                               {"state": "off", "last_changed": "2026-10-25T21:05:00+00:00"}] for e in eids])


async def template(req):
    auth(req)
    body = await req.json()
    return web.Response(text=f"rendered:{body['template']}")


async def services(req):
    auth(req)
    DB["calls"].append([req.match_info["domain"], req.match_info["service"], await req.json()])
    return web.json_response([])


async def automation_cfg(req):
    auth(req)
    cid = req.match_info["cid"]
    if req.method == "GET":
        if cid not in DB["automations"]:
            raise web.HTTPNotFound()
        return web.json_response(DB["automations"][cid])
    if req.method == "DELETE":
        DB["automations"].pop(cid, None)
        return web.json_response({"result": "ok"})
    body = await req.json()
    DB["automations"][cid] = {"id": cid, **{k: v for k, v in body.items() if k != "id"}}
    return web.json_response({"result": "ok"})


async def diag(req):
    auth(req)
    return web.json_response({"options": {"mode": "bridge", "filter": {"include_domains": [], "include_entities": ["binary_sensor.a", "binary_sensor.b"]}},
                              "accessories": [{"aid": 1}, {"aid": 2}], "data": {"x": 1}})


def ws_handle(msg):
    t = msg["type"]
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
    web.route("*", "/api/config/automation/config/{cid}", automation_cfg),
    web.get("/api/diagnostics/config_entry/{eid}", diag),
    web.get("/api/websocket", websocket),
])

if __name__ == "__main__":
    web.run_app(app, port=int(sys.argv[1]), print=None)
