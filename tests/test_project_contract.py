"""公开项目契约：发布元数据、模板与维护文档必须相互一致。"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_RELEASE = "6.2.0"
EXPECTED_CONFIG_SCHEMA = "6.1.0"


def source_constant(name: str) -> str:
    text = (ROOT / "plugin.py").read_text(encoding="utf-8")
    match = re.search(rf"^{name}\s*=\s*['\"]([^'\"]+)['\"]", text, re.MULTILINE)
    if match is None:
        raise AssertionError(f"plugin.py 缺少 {name} 常量")
    return match.group(1)


class ProjectContractTests(unittest.TestCase):
    def test_release_metadata_has_one_truth(self) -> None:
        manifest = json.loads((ROOT / "_manifest.json").read_text(encoding="utf-8"))

        self.assertEqual(source_constant("PLUGIN_VERSION"), EXPECTED_RELEASE)
        self.assertEqual(manifest["version"], EXPECTED_RELEASE)
        self.assertIn(f"v{EXPECTED_RELEASE}", (ROOT / "README.md").read_text(encoding="utf-8"))
        self.assertIn(f"v{EXPECTED_RELEASE}", (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))
        self.assertIn(f"v{EXPECTED_RELEASE}", (ROOT / "HANDOVER.md").read_text(encoding="utf-8"))

    def test_schema_version_is_not_masqueraded_as_release_version(self) -> None:
        example = (ROOT / "config.toml.example").read_text(encoding="utf-8")
        match = re.search(
            r"^\[plugin\][\s\S]*?^config_version\s*=\s*['\"]([^'\"]+)['\"]",
            example,
            re.MULTILINE,
        )

        self.assertIsNotNone(match, "config.toml.example 缺少 [plugin].config_version")
        self.assertEqual(source_constant("CONFIG_SCHEMA_VERSION"), EXPECTED_CONFIG_SCHEMA)
        self.assertEqual(match.group(1), EXPECTED_CONFIG_SCHEMA)

    def test_single_canonical_template_and_backup_exclusion(self) -> None:
        self.assertTrue((ROOT / "config.toml.example").is_file())
        self.assertFalse((ROOT / "config_template.toml").exists())
        ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
        ignored_lines = {line.strip() for line in ignored.splitlines()}
        self.assertIn("*.bak", ignored_lines)
        self.assertIn("*.bak.*", ignored_lines)

    def test_bootstrap_instructions_preserve_existing_config(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn(
            "if [ ! -e plugins/hltv_plugin/config.toml ]; then",
            readme,
        )

    def test_declared_dependencies_cover_direct_requests_import(self) -> None:
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")

        self.assertRegex(requirements, r"(?m)^requests(?:[<>=!~ ].*)?$")

    def test_docs_list_only_implemented_live_providers(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        providers = (ROOT / "live_providers.py").read_text(encoding="utf-8")

        self.assertIn("BO3.gg", readme)
        self.assertIn("PandaScore", readme)
        self.assertNotIn("Playwright", readme)
        self.assertNotIn("Playwright", providers)
        handover = (ROOT / "HANDOVER.md").read_text(encoding="utf-8")
        self.assertNotIn("Playwright", handover)

    def test_current_docs_do_not_advertise_retired_stack(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        handover = (ROOT / "HANDOVER.md").read_text(encoding="utf-8")

        self.assertNotIn("v5.1.0", readme)
        self.assertNotIn("hltv-api.vercel.app", readme)
        self.assertIn("不要复活 `hltv-api.vercel.app`", handover)
        self.assertIn("Jina Reader", readme)
        self.assertIn("Tavily Extract", readme)


if __name__ == "__main__":
    unittest.main()
