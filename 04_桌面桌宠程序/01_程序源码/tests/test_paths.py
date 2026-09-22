import sqlite3
import tempfile
import unittest
import os
from pathlib import Path
from unittest.mock import patch

from coco import paths


class PathTests(unittest.TestCase):
    def test_default_nova_instance_signature_is_distinct(self):
        local_app_data = Path(tempfile.mkdtemp())
        with patch.dict(os.environ, {"LOCALAPPDATA": str(local_app_data), "COCO_INSTANCE_DIR": ""}, clear=False):
            with patch.object(paths, "FROZEN", True):
                self.assertEqual(paths.instance_namespace(), (local_app_data / "NovaOrbDesktop-v020").resolve())
                self.assertTrue(paths.instance_server_name().startswith("nova-orb-"))
                self.assertFalse(paths.instance_server_name().startswith("coco-"))

    def test_source_and_frozen_instance_namespace_share_user_directory(self):
        package = Path(tempfile.mkdtemp()) / "package"
        data = Path(tempfile.mkdtemp()) / "CocoDesktop"
        with patch.dict(os.environ, {"COCO_INSTANCE_DIR": str(data)}, clear=False):
            with patch.object(paths, "FROZEN", True), patch.object(paths, "DATA", data), patch.object(paths, "ROOT", package):
                self.assertEqual(paths.instance_namespace(), data.resolve())
                frozen_server = paths.instance_server_name()
            with patch.object(paths, "FROZEN", False), patch.object(paths, "DATA", package / "legacy-data"), patch.object(paths, "ROOT", package):
                self.assertEqual(paths.instance_namespace(), data.resolve())
                self.assertEqual(paths.instance_server_name(), frozen_server)

    def test_legacy_database_is_backed_up_once_without_deleting_source(self):
        root = Path(tempfile.mkdtemp())
        package = root / "04_桌面桌宠程序" / "05_可运行版本" / "Coco"
        package.mkdir(parents=True)
        (root / "项目资料存放说明.md").write_text("marker", encoding="utf-8")
        legacy = root / "05_记忆与状态数据" / "01_本地数据库" / "coco.sqlite3"
        legacy.parent.mkdir(parents=True)
        with sqlite3.connect(legacy) as db:
            db.execute("CREATE TABLE marker (value TEXT)")
            db.execute("INSERT INTO marker VALUES ('legacy')")
        data = root / "user-data"
        with patch.object(paths, "FROZEN", True), patch.object(paths, "APP_DIR", package), patch.object(paths, "DATA", data):
            target = paths.migrate_legacy()
            self.assertEqual(target, data / "01_本地数据库/coco.sqlite3")
            self.assertTrue(legacy.is_file())
            with sqlite3.connect(target) as db:
                self.assertEqual(db.execute("SELECT value FROM marker").fetchone()[0], "legacy")
            self.assertIsNone(paths.migrate_legacy())


if __name__ == "__main__":
    unittest.main()
