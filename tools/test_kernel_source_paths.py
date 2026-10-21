"""The source check must distinguish build paths from Linux's workqueue names."""
import io
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest


CHECK = Path(__file__).parent / "linux/athena/kernel/check-source-paths.sh"


class SourcePaths(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.baseline = self.root / "base.tar.xz"
        self.candidate = self.root / "new.tar.xz"
        self.archive(self.baseline, "linux/README", b"baseline\n")
        self.archive(self.candidate, "linux/README", b"source\n")
        bindir = self.root / "bin"
        bindir.mkdir()
        identity = bindir / "id"
        identity.write_text("#!/bin/sh\nprintf 'root\\n'\n")
        identity.chmod(0o755)
        self.env = {**os.environ, "PATH": str(bindir) + os.pathsep + os.environ["PATH"],
                    "USER": "root", "SUDO_USER": ""}

    def archive(self, path, name, content):
        with tarfile.open(path, "w:xz") as archive:
            info = tarfile.TarInfo(name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))

    def run_check(self, work="/work", ktree="/work/linux-6.18.56"):
        return subprocess.run(
            ["bash", str(CHECK), str(self.candidate), str(self.baseline), work, ktree],
            capture_output=True, text=True, env=self.env)

    def check(self, name, content):
        self.archive(self.candidate, name, content)
        return self.run_check()

    def test_unreadable_archive_cannot_report_success(self):
        for path in (self.candidate, self.baseline):
            valid = path.read_bytes()
            for kind, bad in (("missing", None), ("malformed", b"not an xz archive"),
                              ("truncated", valid[:-12])):
                with self.subTest(archive=path.name, kind=kind):
                    if bad is None:
                        path.unlink()
                    else:
                        path.write_bytes(bad)
                    result = self.run_check()
                    path.write_bytes(valid)
                    self.assertNotEqual(result.returncode, 0, result.stdout)
                    self.assertNotIn("OK:", result.stdout)

    def test_workqueue_is_source_not_a_build_path(self):
        result = self.check("linux/Documentation/core-api/workqueue.rst",
                            b"#include <linux/workqueue.h>\n")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_actual_build_paths_are_refused(self):
        for content in (b"/work/linux-6.18.56/source.c\n", b'build root: "/work"\n'):
            with self.subTest(content=content):
                self.assertNotEqual(self.check("linux/README", content).returncode, 0)

    def test_build_path_in_archive_name_is_refused(self):
        self.assertNotEqual(self.check("/work/copied-source.c", b"source\n").returncode, 0)

    def test_trailing_slashes_do_not_hide_build_paths(self):
        for work, ktree, content in (("/work///", "/tree///", b"/work/source.c\n"),
                                     ("/work/", "/tree/", b"/tree/source.c\n")):
            with self.subTest(work=work, ktree=ktree, content=content):
                self.archive(self.candidate, "linux/README", content)
                result = self.run_check(work, ktree)
                self.assertNotEqual(result.returncode, 0, result.stdout)

    def test_root_or_relative_build_directories_are_usage_errors(self):
        for work, ktree in (("/", "/tree"), ("/work", "///"),
                            ("", "/tree"), ("/work", "tree")):
            with self.subTest(work=work, ktree=ktree):
                result = self.run_check(work, ktree)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
