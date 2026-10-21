"""Docker integration fixtures; requires the existing Athena build image.

    TECHO5_TEST_DOCKER=1 python3 tools/test_athena_docker_build.py

The CLI shim skips image construction and scopes container/volume names to the fixture.
Docker handles mounts, container execution and signals. No kernel is built or device contacted.
"""
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time
import unittest
import uuid


WRAPPER = Path(__file__).parent / "linux/athena/kernel/build-in-docker.sh"
IMAGE = "techo5-athena-kbuild:ubuntu24.04"


@unittest.skipUnless(os.environ.get("TECHO5_TEST_DOCKER") == "1", "opt-in Docker integration")
class DockerBuild(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docker = shutil.which("docker")
        if not cls.docker:
            raise unittest.SkipTest("Docker CLI is unavailable")
        result = subprocess.run([cls.docker, "image", "inspect", IMAGE], capture_output=True)
        if result.returncode:
            raise unittest.SkipTest("build the Athena Docker image first")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="athena-docker-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.name = "athena-fixture-" + uuid.uuid4().hex
        self.addCleanup(self.clean_docker)
        self.repo = self.root / "Checkout, fixture"
        here = self.repo / "tools/linux/athena/kernel"
        here.mkdir(parents=True)
        self.wrapper = here / WRAPPER.name
        shutil.copyfile(WRAPPER, self.wrapper)
        self.build = here / "build.sh"
        self.out = self.root / "Output, fixture"
        bindir = self.root / "bin"
        bindir.mkdir()
        shim = bindir / "docker"
        shim.write_text('''#!/usr/bin/env python3
import os
import sys
args = sys.argv[1:]
if args[0] == "build":
    sys.exit(0)
name = os.environ["ATHENA_FIXTURE_NAME"]
args = [name if arg == "techo5-athena-kbuild" else
        arg.replace("src=techo5-athena-kbuild,dst=/work", "src=" + name + ",dst=/work")
        for arg in args]
if args[0] in ("run", "create"):
    args[1:1] = ["--network", "none"]
docker = os.environ["ATHENA_FIXTURE_DOCKER"]
os.execv(docker, [docker] + args)
''')
        shim.chmod(0o755)
        self.env = {**os.environ, "PATH": str(bindir) + os.pathsep + os.environ["PATH"],
                    "OUT": str(self.out), "ATHENA_FIXTURE_NAME": self.name,
                    "ATHENA_FIXTURE_DOCKER": self.docker}

    def clean_docker(self):
        for args in (("rm", "-f", self.name), ("volume", "rm", self.name)):
            subprocess.run([self.docker, *args], capture_output=True, timeout=15)

    def run_wrapper(self):
        return subprocess.run(["bash", str(self.wrapper)], env=self.env,
                              capture_output=True, text=True, timeout=30)

    def container_exists(self):
        return subprocess.run([self.docker, "container", "inspect", self.name],
                              capture_output=True).returncode == 0

    def test_comma_paths_preserve_readonly_checkout_and_writable_output(self):
        self.build.write_text('''#!/bin/bash
set -eu
if touch /repo/must-not-write 2>/dev/null; then exit 91; fi
printf built > "$OUT/result"
''')
        result = self.run_wrapper()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.out / "result").read_text(), "built")
        self.assertFalse((self.repo / "must-not-write").exists())
        self.assertFalse(self.container_exists())

    def test_build_failure_is_returned_and_container_removed(self):
        self.build.write_text("exit 7\n")
        result = self.run_wrapper()
        self.assertEqual(result.returncode, 7, result.stdout + result.stderr)
        self.assertFalse(self.container_exists())

    def test_cancellation_removes_running_build(self):
        self.build.write_text('printf started > "$OUT/started"\nsleep 300\n')
        for sig, status in ((signal.SIGINT, 130), (signal.SIGTERM, 143)):
            with self.subTest(signal=sig):
                marker = self.out / "started"
                marker.unlink(missing_ok=True)
                proc = subprocess.Popen(["bash", str(self.wrapper)], env=self.env,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        text=True, start_new_session=True)
                try:
                    deadline = time.monotonic() + 15
                    while not marker.exists() and proc.poll() is None and time.monotonic() < deadline:
                        time.sleep(0.05)
                    self.assertTrue(marker.exists(), "fixture build did not start")
                    proc.send_signal(sig)
                    stdout, stderr = proc.communicate(timeout=8)
                    self.assertEqual(proc.returncode, status, stdout + stderr)
                    self.assertFalse(self.container_exists())
                finally:
                    if proc.poll() is None:
                        os.killpg(proc.pid, signal.SIGKILL)
                    self.clean_docker()
                    proc.communicate(timeout=15)

    def test_name_conflict_preserves_existing_container(self):
        self.build.write_text("exit 0\n")
        subprocess.run([self.docker, "run", "--detach", "--network", "none",
                        "--name", self.name, IMAGE, "sleep", "300"],
                       check=True, capture_output=True, timeout=15)
        result = self.run_wrapper()
        self.assertNotEqual(result.returncode, 0)
        state = subprocess.run([self.docker, "container", "inspect", "--format", "{{.State.Running}}", self.name],
                               check=True, capture_output=True, text=True)
        self.assertEqual(state.stdout.strip(), "true")


if __name__ == "__main__":
    unittest.main()
