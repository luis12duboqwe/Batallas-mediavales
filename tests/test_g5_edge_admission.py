"""Adversarial regression tests for the host/runtime admission gate."""
import json
import os
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ops.g5_edge_admission import EdgeAdmission, EdgeError


class FakeEdge:
    def __init__(self, root):
        self.root = root
        self.state = root / ".ops-state"
        self.state.mkdir(mode=0o700)
        self.edge = self.state / "edge-maintenance"
        self.edge.mkdir(mode=0o755)
        self.open = self.edge / "open"
        self.open.mkdir(mode=0o755)
        self.config = root / "nginx.g5.conf"
        self.config.write_text("fixture")
        self.identity = "a" * 64
        self.probes = []
        self.status = (1, "", "  HTTP/1.1 503 Service Temporarily Unavailable\n")
        self.stale = False
        self.row = {
            "id": self.identity, "project": "fixture", "service": "nginx",
            "running": True, "paused": False,
            "mounts": [
                {"Type": "bind", "Source": str(self.edge),
                 "Destination": "/etc/nginx/edge-maintenance", "RW": False},
                {"Type": "bind", "Source": str(self.config),
                 "Destination": "/etc/nginx/nginx.conf", "RW": False},
            ],
        }

    def run(self, args):
        if args[0] == "inspect":
            return json.dumps(self.row)
        assert args[:2] == ["exec", self.identity]
        if self.stale:
            return "0:0"
        info = (self.edge if args[-1].endswith("edge-maintenance") else self.config).stat()
        return f"{info.st_dev}:{info.st_ino}"

    def probe(self, args):
        assert not self.open.exists()
        self.probes.append(args)
        return self.status

    def gate(self):
        return EdgeAdmission(str(self.root), "fixture", self.identity, self.run, self.probe)


def test_close_pins_mounts_removes_marker_and_probes_all_routes(tmp_path):
    edge = FakeEdge(tmp_path)
    gate = edge.gate()
    gate.close()
    assert not edge.open.exists()
    assert len(edge.probes) == 5
    assert any("Upgrade: websocket" in args for args in edge.probes)
    gate.assert_closed()
    assert len(edge.probes) == 10
    # Idempotent closure is safe; never creates an open marker.
    gate.close()
    assert not edge.open.exists()


@pytest.mark.parametrize("change", ["rw", "wrong-source", "wrong-project", "wrong-service",
                                     "stale-inode", "nested-mount", "stopped", "config-symlink"])
def test_wrong_runtime_refused_before_removing_marker(tmp_path, change):
    edge = FakeEdge(tmp_path)
    if change == "rw":
        edge.row["mounts"][0]["RW"] = True
    elif change == "wrong-source":
        edge.row["mounts"][0]["Source"] = "/unrelated"
    elif change == "wrong-project":
        edge.row["project"] = "unrelated"
    elif change == "wrong-service":
        edge.row["service"] = "backend"
    elif change == "stale-inode":
        edge.stale = True
    elif change == "nested-mount":
        edge.row["mounts"].append({"Destination": "/etc/nginx/edge-maintenance/open"})
    elif change == "stopped":
        edge.row["running"] = False
    else:
        edge.config.unlink()
        edge.config.symlink_to("/dev/null")
    with pytest.raises(EdgeError):
        edge.gate().close()
    assert edge.open.is_dir()
    assert not edge.probes


@pytest.mark.parametrize("kind", ["symlink", "regular", "nonempty", "extra", "fifo"])
def test_unsafe_marker_never_removed_recursively(tmp_path, kind):
    edge = FakeEdge(tmp_path)
    if kind == "nonempty":
        (edge.open / "data").write_text("do not remove")
    elif kind == "extra":
        (edge.edge / "unexpected").touch()
    else:
        edge.open.rmdir()
        if kind == "symlink":
            edge.open.symlink_to(tmp_path)
        elif kind == "regular":
            edge.open.touch()
        else:
            os.mkfifo(edge.open)
    with pytest.raises(EdgeError):
        edge.gate().close()
    assert os.path.lexists(edge.open)
    assert not edge.probes


@pytest.mark.parametrize("response", [
    (1, "", "connection refused"),
    (1, "", "HTTP/1.1 302 Found\nHTTP/1.1 503 Service Unavailable\n"),
    (0, "", "HTTP/1.1 503 Service Unavailable\n"),
    (1, "", "HTTP/1.1 429 Too Many Requests\n"),
    (1, "", "HTTP/1.1 502 Bad Gateway\n"),
])
def test_failure_after_marker_removal_keeps_admission_closed(tmp_path, response):
    edge = FakeEdge(tmp_path)
    edge.status = response
    gate = edge.gate()
    with pytest.raises(EdgeError):
        gate.close()
    assert not edge.open.exists()
    with pytest.raises(EdgeError):
        gate.assert_closed()


@pytest.mark.parametrize("change", ["reopen", "replace-dir", "stale-runtime"])
def test_detect_drift_after_closure(tmp_path, change):
    edge = FakeEdge(tmp_path)
    gate = edge.gate()
    gate.close()
    if change == "reopen":
        edge.open.mkdir()
    elif change == "replace-dir":
        edge.edge.rename(edge.state / "old")
        edge.edge.mkdir(mode=0o755)
    else:
        edge.stale = True
    with pytest.raises(EdgeError):
        gate.assert_closed()


def test_edge_dir_symlink_is_not_followed(tmp_path):
    edge = FakeEdge(tmp_path)
    edge.edge.rename(edge.state / "target")
    edge.edge.symlink_to(edge.state / "target")
    with pytest.raises(EdgeError):
        edge.gate().close()
    assert (edge.state / "target" / "open").is_dir()
