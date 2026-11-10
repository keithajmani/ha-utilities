"""End-to-end tests: run ha.py against the fake Home Assistant in mock_ha.py."""
import json
import os
import re
import socket
import subprocess
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HA_PY = os.path.join(ROOT, "ha.py")
MOCK = os.path.join(ROOT, "tests", "mock_ha.py")


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def ha(tmp_path):
    """Start a fresh mock HA and return a function that runs ha.py against it."""
    port = _free_port()
    proc = subprocess.Popen([sys.executable, MOCK, str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.1).close()
            break
        except OSError:
            time.sleep(0.1)
    home = tmp_path / "home"
    home.mkdir()
    (home / "url").write_text(f"http://127.0.0.1:{port}\n")
    (home / "token").write_text("test-token\n")
    (home / "ha.toml").write_text('protected_dashboards = ["dashboard-generated"]\n')
    for cmd in (["init", "-q"], ["config", "user.email", "t@example.com"], ["config", "user.name", "test"]):
        subprocess.run(["git", "-C", str(home), *cmd], check=True)

    def run(*args):
        env = dict(os.environ, HA_HOME=str(home))
        r = subprocess.run([sys.executable, HA_PY, *args], capture_output=True, text=True, env=env)
        return r.returncode, r.stdout, r.stderr

    run.home = home
    yield run
    proc.terminate()
    proc.wait()


def plan_id(out):
    m = re.search(r"^PLAN (\w+)", out, re.M)
    assert m, out
    return m.group(1)


def test_state_glob_and_json(ha):
    rc, out, _ = ha("state", "media_player.*")
    assert rc == 0
    assert "media_player.kitchen_speaker" in out and "media_player.office_speaker" in out
    rc, out, _ = ha("state", "switch.porch_light", "--json")
    assert json.loads(out) == [{"entity": "switch.porch_light", "state": "off"}]


def test_reads_run(ha):
    for args in (["areas"], ["entities"], ["devices"], ["exposed"], ["repairs"], ["logs"], ["dashboard", "list"],
                 ["backups"], ["history", "switch.porch_light"], ["homekit", "list"], ["template", "{{ 1 }}"]):
        rc, out, err = ha(*args)
        assert rc == 0, (args, err)


def test_backup_key_is_redacted(ha):
    rc, out, _ = ha("backup", "config")
    assert rc == 0
    assert "SECRET-KEY" not in out
    assert json.loads(out)["encryption_key"] == "«redacted»"


def test_entries_hide_ignored(ha):
    rc, out, _ = ha("entries", "--problems")
    assert "Patio Plug" in out and "Old Camera" not in out
    rc, out, _ = ha("entries", "--problems", "--ignored")
    assert "Old Camera" in out and "ignored=yes" in out


def test_write_is_dry_run_without_yes(ha):
    rc, out, _ = ha("entity", "set", "switch.porch_light", "--area", "office")
    assert rc == 0 and "dry run, nothing changed" in out
    rc, out, _ = ha("entities", "--search", "porch")
    assert "Front Porch" in out


def test_wrong_plan_id_is_refused(ha):
    rc, _, err = ha("entity", "set", "switch.porch_light", "--area", "office", "--yes", "--plan", "000000")
    assert rc == 3 and "plan id mismatch" in err


def test_apply_snapshot_git_and_restore(ha):
    args = ["entity", "set", "switch.porch_light", "--area", "office"]
    pid = plan_id(ha(*args)[1])
    rc, out, _ = ha(*args, "--yes", "--plan", pid)
    assert rc == 0 and "APPLIED" in out and "verified by read-back" in out
    assert "Office" in ha("entities", "--search", "porch")[1]
    snap = re.search(r"UNDO  ha.py restore (\S+)", out).group(1)
    log = subprocess.run(["git", "-C", str(ha.home), "log", "--oneline"], capture_output=True, text=True).stdout
    assert "entity-set (before)" in log and "entity-set (after)" in log

    rpid = plan_id(ha("restore", snap)[1])
    rc, out, _ = ha("restore", snap, "--yes", "--plan", rpid)
    assert rc == 0 and "APPLIED" in out
    assert "Front Porch" in ha("entities", "--search", "porch")[1]


def test_no_change_needed(ha):
    rc, out, _ = ha("entity", "set", "switch.porch_light", "--area", "front_porch")
    assert rc == 0 and "no change needed" in out


def test_protected_dashboard_refused(ha, tmp_path):
    f = tmp_path / "d.json"
    f.write_text(json.dumps({"views": []}))
    rc, _, err = ha("dashboard", "save", "dashboard-generated", "--from", str(f))
    assert rc == 3 and "protected" in err


def test_dashboard_save_and_diff(ha, tmp_path):
    f = tmp_path / "d.json"
    rc, out, _ = ha("dashboard", "get", "lovelace-media", "--out", str(f))
    cfg = json.loads(f.read_text())
    cfg["views"][0]["cards"].append({"type": "markdown", "content": "hi"})
    f.write_text(json.dumps(cfg))
    args = ["dashboard", "save", "lovelace-media", "--from", str(f)]
    out = ha(*args)[1]
    assert "1 views, 1 cards → 1 views, 2 cards" in out and '"content": "hi"' in out
    rc, out, _ = ha(*args, "--yes", "--plan", plan_id(out))
    assert rc == 0 and "verified by read-back" in out


def test_automation_create_then_restore_removes_it(ha, tmp_path):
    f = tmp_path / "a.json"
    f.write_text(json.dumps({"alias": "Test", "triggers": [], "actions": []}))
    rc, _, err = ha("automation", "save", "999", "--from", str(f))
    assert rc != 0 and "--create" in err
    args = ["automation", "save", "999", "--from", str(f), "--create"]
    out = ha(*args, "--yes", "--plan", plan_id(ha(*args)[1]))[1]
    snap = re.search(r"UNDO  ha.py restore (\S+)", out).group(1)
    out = ha("restore", snap, "--yes", "--plan", plan_id(ha("restore", snap)[1]))[1]
    assert "verified by read-back" in out
    assert ha("automation", "get", "999")[0] != 0


def test_service_call_has_no_undo(ha):
    args = ["call", "notify.send_message", "--entity", "notify.kitchen_speaker", "--data", '{"message":"hi"}']
    out = ha(*args)[1]
    assert "no automatic undo" in out
    rc, out, _ = ha(*args, "--yes", "--plan", plan_id(out))
    assert rc == 0 and "APPLIED" in out and "UNDO" not in out


def test_bad_token(ha):
    (ha.home / "token").write_text("wrong\n")
    rc, _, err = ha("state", "switch.porch_light")
    assert rc == 1 and "token rejected" in err


def test_history_window_runs_to_now(ha):
    # HA ends the window one day after the start unless end_time is sent; ha.py must send it
    rc, out, err = ha("history", "switch.porch_light", "--since", "2026-10-25T00:00+00:00", "--json")
    assert rc == 0, err
    assert [r["state"] for r in json.loads(out)] == ["on", "off", "on"]
    rc, out, _ = ha("history", "switch.porch_light", "--since", "2026-10-25T00:00+00:00",
                    "--until", "2026-10-26T00:00+00:00", "--json")
    assert [r["state"] for r in json.loads(out)] == ["on", "off"]


def test_stats_find_and_read(ha):
    rc, out, err = ha("stats", "--find", "laundry")
    assert rc == 0, err
    assert "sensor.laundry_temperature" in out and "porch" not in out
    rc, out, err = ha("stats", "sensor.laundry_temperature", "--since", "30d", "--json")
    assert rc == 0, err
    rows = json.loads(out)
    assert [r["mean"] for r in rows] == [20.5, 22.25] and rows[1]["max"] == 24.0
    rc, _, err = ha("stats")
    assert rc == 1 and "--find" in err


def test_automation_traces_and_trace(ha):
    rc, out, err = ha("automation", "traces", "automation.garage_door_open_alert")
    assert rc == 0, err
    lines = out.splitlines()
    assert "result=error" in lines[0] and "run=r2" in lines[0]
    assert "result=failed_conditions" in lines[1] and "step=condition/0" in lines[1]
    rc, out, err = ha("automation", "trace", "automation.garage_door_open_alert")
    assert rc == 0, err
    assert 'what="Tell the kitchen"' in out and 'result="called notify.send_message"' in out
    assert "ERROR  Action notify.send_message not found" in out
    rc, out, _ = ha("automation", "trace", "1700000000001", "--run", "2")
    assert "condition/0" in out and "result=false" in out and "action/0" not in out
    rc, _, err = ha("automation", "trace", "1700000000001", "--run", "9")
    assert rc == 1 and "1 to 2" in err
    rc, _, err = ha("script", "trace", "script.nothing")
    assert rc == 1 and "no stored traces" in err


def test_scene_save_and_restore(ha, tmp_path):
    f = tmp_path / "s.json"
    ha("scene", "get", "scene.movie_night", "--out", str(f))
    cfg = json.loads(f.read_text())
    cfg["entities"]["switch.porch_light"] = "on"
    f.write_text(json.dumps(cfg))
    args = ["scene", "save", "scene.movie_night", "--from", str(f)]
    out = ha(*args, "--yes", "--plan", plan_id(ha(*args)[1]))[1]
    assert "verified by read-back" in out
    assert '"on"' in ha("scene", "get", "1700000000101")[1]
    snap = re.search(r"UNDO  ha.py restore (\S+)", out).group(1)
    ha("restore", snap, "--yes", "--plan", plan_id(ha("restore", snap)[1]))
    assert '"off"' in ha("scene", "get", "1700000000101")[1]


def test_helper_save_shows_fields_and_restores(ha, tmp_path):
    f = tmp_path / "h.yaml"
    f.write_text("name: Bedtime volume\nmin: 0\nmax: 60\nstep: 5\n")
    args = ["helper", "save", "input_number.bedtime_volume", "--from", str(f)]
    out = ha(*args)[1]
    assert "max: 100 → 60" in out and "mode: slider → (none)" in out  # a field left out is removed
    out = ha(*args, "--yes", "--plan", plan_id(out))[1]
    assert "verified by read-back" in out
    snap = re.search(r"UNDO  ha.py restore (\S+)", out).group(1)
    out = ha("restore", snap, "--yes", "--plan", plan_id(ha("restore", snap)[1]))[1]
    assert "verified by read-back" in out
    assert "max: 100" in ha("helper", "get", "input_number.bedtime_volume", "--yaml")[1]


def test_helper_create_then_restore_removes_it(ha, tmp_path):
    f = tmp_path / "h.yaml"
    f.write_text("name: Movie mode\nicon: mdi:movie\n")
    rc, _, err = ha("helper", "save", "input_boolean", "--from", str(f))
    assert rc != 0 and "--create" in err
    rc, _, err = ha("helper", "save", "input_boolean.guest_mode", "--from", str(f), "--create")
    assert rc != 0 and "already exists" in err
    args = ["helper", "save", "input_boolean", "--from", str(f), "--create"]
    out = ha(*args, "--yes", "--plan", plan_id(ha(*args)[1]))[1]
    assert "verified by read-back" in out
    assert "input_boolean.movie_mode" in ha("helper", "list")[1]
    snap = re.search(r"UNDO  ha.py restore (\S+)", out).group(1)
    out = ha("restore", snap)[1]
    assert "movie_mode  exists: True → False" in out
    out = ha("restore", snap, "--yes", "--plan", plan_id(out))[1]
    assert "verified by read-back" in out
    assert "movie_mode" not in ha("helper", "list")[1]


def test_helper_rejects_yaml_and_other_types(ha):
    rc, _, err = ha("helper", "get", "switch.porch_light")
    assert rc == 1 and "not a helper type" in err
    rc, _, err = ha("helper", "get", "input_boolean.nope")
    assert rc == 1 and "not a UI helper" in err
