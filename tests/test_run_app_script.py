from __future__ import annotations

import os
import socket
import subprocess
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "run_app.ps1"


@unittest.skipUnless(os.name == "nt", "run_app.ps1 is Windows-only")
class RunAppScriptTests(unittest.TestCase):
    def test_launcher_auto_detects_local_v2ray_socks_proxy_without_persisting_subscriptions(self):
        source = SCRIPT.read_text(encoding="utf-8")

        self.assertIn("CINESCOPE_OUTBOUND_PROXY", source)
        self.assertIn("CINESCOPE_PROXY_MODE", source)
        self.assertIn('CINESCOPE_PROXY_MODE = "fallback"', source)
        self.assertIn("socks5h://127.0.0.1:10808", source)
        self.assertIn("Test-PortOpen -TargetPort 10808", source)
        self.assertNotIn("liangxin.xyz", source)

    def _free_port(self) -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    def _run(self, *arguments: str, env: dict[str, str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(SCRIPT),
                *arguments,
            ],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )

    def _wait_for_port(self, port: int, *, open_: bool, timeout: float = 20.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(0.25)
                connected = sock.connect_ex(("127.0.0.1", port)) == 0
            if connected is open_:
                return
            time.sleep(0.1)
        self.fail(f"port {port} did not become {'open' if open_ else 'closed'}")

    def test_launcher_restarts_verified_server_tracks_pid_and_stops_cleanly(self):
        port = self._free_port()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            runtime_dir = temp_root / "runtime"
            env = os.environ.copy()
            env["CINESCOPE_DATA_DIR"] = str(temp_root / "data")
            common = (
                "-Port",
                str(port),
                "-RuntimeDirectory",
                str(runtime_dir),
                "-NoBrowser",
            )
            try:
                started = self._run(*common, env=env)
                self.assertEqual(0, started.returncode, started.stdout + started.stderr)
                self._wait_for_port(port, open_=True)

                pid_file = runtime_dir / f"server-{port}.pid"
                self.assertTrue(pid_file.is_file())
                server_pid = int(pid_file.read_text(encoding="ascii").strip())
                self.assertGreater(server_pid, 0)
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5) as response:
                    self.assertEqual(200, response.status)

                restarted = self._run(*common, env=env)
                self.assertEqual(0, restarted.returncode, restarted.stdout + restarted.stderr)
                replacement_pid = int(pid_file.read_text(encoding="ascii").strip())
                self.assertNotEqual(server_pid, replacement_pid)
                self._wait_for_port(port, open_=True)

                stopped = self._run(*common, "-Stop", env=env)
                self.assertEqual(0, stopped.returncode, stopped.stdout + stopped.stderr)
                self._wait_for_port(port, open_=False)
                self.assertFalse(pid_file.exists())
            finally:
                self._run(*common, "-Stop", env=env, timeout=30)


if __name__ == "__main__":
    unittest.main()
