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
    def check(self, name, content):
        with tempfile.TemporaryDirectory() as tmp:
            baseline, candidate = Path(tmp) / "base.tar.xz", Path(tmp) / "new.tar.xz"
            for path, member, data in ((baseline, "linux/README", b"baseline\n"),
                                       (candidate, name, content)):
                with tarfile.open(path, "w:xz") as archive:
                    info = tarfile.TarInfo(member)
                    info.size = len(data)
                    archive.addfile(info, io.BytesIO(data))
            return subprocess.run(
                ["bash", str(CHECK), str(candidate), str(baseline), "/work", "/work/linux-6.18.56"],
                capture_output=True, text=True, env={**os.environ, "USER": "root", "SUDO_USER": ""})

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


if __name__ == "__main__":
    unittest.main()
