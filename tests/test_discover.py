from __future__ import annotations

import io
import unittest
import zipfile

from sylvanova_apworld_bot.discover import (
	DiscoveryError,
	build_url_or_template,
	coerce_semver,
	derive_version,
	discover_from_release_url,
	extract_apworld_id,
	extract_game_name,
	manual_display_name,
	parse_github_release_asset_url,
)
from sylvanova_apworld_bot.toml_template import render_discovered_toml


def _make_apworld(package: str, init_source: str) -> bytes:
	buffer = io.BytesIO()
	with zipfile.ZipFile(buffer, "w") as archive:
		archive.writestr(f"{package}/__init__.py", init_source)
		archive.writestr(f"{package}/Items.py", "# items\n")
	return buffer.getvalue()


class ParseUrlTests(unittest.TestCase):
	def test_parses_release_asset(self) -> None:
		url = "https://github.com/Ishigh1/Archipelago/releases/download/2048-1.1.2/2048.apworld"
		asset = parse_github_release_asset_url(url)
		self.assertEqual(asset.owner, "Ishigh1")
		self.assertEqual(asset.repo, "Archipelago")
		self.assertEqual(asset.tag, "2048-1.1.2")
		self.assertEqual(asset.asset, "2048.apworld")
		self.assertEqual(asset.home, "https://github.com/Ishigh1/Archipelago")

	def test_rejects_release_page(self) -> None:
		with self.assertRaises(DiscoveryError) as ctx:
			parse_github_release_asset_url(
				"https://github.com/Ishigh1/Archipelago/releases/tag/2048-1.1.2"
			)
		self.assertIn("direct GitHub release asset", str(ctx.exception))

	def test_rejects_non_github(self) -> None:
		with self.assertRaises(DiscoveryError):
			parse_github_release_asset_url(
				"https://example.com/files/world.apworld"
			)


class SemverTests(unittest.TestCase):
	def test_coerce_short_version(self) -> None:
		self.assertEqual(coerce_semver("0.8"), "0.8.0")
		self.assertEqual(coerce_semver("v1.2.3"), "1.2.3")
		self.assertEqual(coerce_semver("1.0.0-beta.1"), "1.0.0-beta.1")

	def test_derive_from_prefixed_tag(self) -> None:
		self.assertEqual(
			derive_version(tag="2048-1.1.2", asset="2048.apworld", apworld_id="2048"),
			"1.1.2",
		)

	def test_derive_from_asset_filename(self) -> None:
		self.assertEqual(
			derive_version(tag="release", asset="demo-0.8.apworld", apworld_id="demo"),
			"0.8.0",
		)

	def test_derive_failure(self) -> None:
		with self.assertRaises(DiscoveryError):
			derive_version(tag="latest", asset="demo.apworld", apworld_id="demo")


class DefaultUrlTests(unittest.TestCase):
	def test_templates_when_version_in_url(self) -> None:
		url = "https://github.com/o/r/releases/download/2048-1.1.2/2048.apworld"
		template, uses = build_url_or_template(url, "1.1.2")
		self.assertTrue(uses)
		self.assertEqual(
			template,
			"https://github.com/o/r/releases/download/2048-{{version}}/2048.apworld",
		)

	def test_keeps_explicit_url_when_version_absent(self) -> None:
		url = "https://github.com/o/r/releases/download/nightly/demo.apworld"
		result, uses = build_url_or_template(url, "1.0.0")
		self.assertFalse(uses)
		self.assertEqual(result, url)


class ManualDisplayNameTests(unittest.TestCase):
	def test_manual_game_author(self) -> None:
		self.assertEqual(
			manual_display_name("Manual_pokemonss_riannehx"),
			"Manual: pokemonss",
		)
		self.assertEqual(
			manual_display_name("Manual_EuroTruckSim2_bdi"),
			"Manual: EuroTruckSim2",
		)

	def test_non_manual(self) -> None:
		self.assertIsNone(manual_display_name("Celeste (Open World)"))


class ArchiveDiscoveryTests(unittest.TestCase):
	def test_extract_id_and_game(self) -> None:
		payload = _make_apworld(
			"DemoWorld",
			'from worlds.AutoWorld import World\n\nclass Demo(World):\n\tgame = "Demo Game"\n',
		)
		apworld_id = extract_apworld_id(payload)
		self.assertEqual(apworld_id, "demoworld")
		self.assertEqual(extract_game_name(payload, apworld_id), "Demo Game")

	def test_full_discover_and_toml(self) -> None:
		payload = _make_apworld(
			"demo",
			'class DemoWorld:\n\tgame = "Demo Game"\n',
		)
		url = "https://github.com/acme/demo/releases/download/demo-1.2.3/demo.apworld"
		world = discover_from_release_url(url, archive_bytes=payload)
		self.assertEqual(world.apworld_id, "demo")
		self.assertEqual(world.name, "Demo Game")
		self.assertEqual(world.version, "1.2.3")
		self.assertEqual(world.home, "https://github.com/acme/demo")
		self.assertTrue(world.uses_default_url)
		self.assertEqual(
			world.url_or_template,
			"https://github.com/acme/demo/releases/download/demo-{{version}}/demo.apworld",
		)
		toml = render_discovered_toml(world)
		self.assertIn('name = "Demo Game"', toml)
		self.assertIn("default_url =", toml)
		self.assertIn('"1.2.3" = {}', toml)

	def test_manual_display_name_in_toml(self) -> None:
		payload = _make_apworld(
			"manual_demo_author",
			'game = "Manual_Demo_Author"\n',
		)
		url = "https://github.com/acme/demo/releases/download/v0.0.1/manual_demo_author.apworld"
		world = discover_from_release_url(url, archive_bytes=payload)
		self.assertEqual(world.display_name, "Manual: Demo")
		toml = render_discovered_toml(world)
		self.assertIn('display_name = "Manual: Demo"', toml)

	def test_resolves_game_from_string_constant(self) -> None:
		buffer = io.BytesIO()
		with zipfile.ZipFile(buffer, "w") as archive:
			archive.writestr(
				"mina_the_hollower/__init__.py",
				"from .constants import MINA_THE_HOLLOWER\n\n"
				"class MinaTheHollowerWorld:\n"
				"\tgame = MINA_THE_HOLLOWER\n",
			)
			archive.writestr(
				"mina_the_hollower/constants.py",
				'MINA_THE_HOLLOWER = "Mina The Hollower"\n',
			)
		payload = buffer.getvalue()
		self.assertEqual(
			extract_game_name(payload, "mina_the_hollower"),
			"Mina The Hollower",
		)

	def test_falls_back_to_archipelago_manifest(self) -> None:
		buffer = io.BytesIO()
		with zipfile.ZipFile(buffer, "w") as archive:
			archive.writestr("demo/__init__.py", "class DemoWorld:\n\tpass\n")
			archive.writestr(
				"demo/archipelago.json",
				'{"game": "Demo From Manifest", "world_version": "1.0.0"}\n',
			)
		payload = buffer.getvalue()
		self.assertEqual(extract_game_name(payload, "demo"), "Demo From Manifest")

	def test_manual_data_game_json_overrides_placeholders(self) -> None:
		buffer = io.BytesIO()
		with zipfile.ZipFile(buffer, "w") as archive:
			archive.writestr(
				"manual_readbooks_roobyroo/data/game.json",
				'{"game": "ReadBooks", "creator": "RoobyRoo"}\n',
			)
			archive.writestr(
				"manual_readbooks_roobyroo/Game.py",
				'game_name = "Manual_%s_%s" % (game_table["game"], game_table["player"])\n',
			)
			archive.writestr(
				"manual_readbooks_roobyroo/Items.py",
				'game = "Manual"\n',
			)
			archive.writestr(
				"manual_readbooks_roobyroo/ManualClient.py",
				'game = "not set"\n',
			)
			archive.writestr(
				"manual_readbooks_roobyroo/manual_test.py",
				"game = game_name\n",
			)
			archive.writestr(
				"manual_readbooks_roobyroo/__init__.py",
				"class ManualWorld:\n\tpass\n",
			)
		payload = buffer.getvalue()
		self.assertEqual(
			extract_game_name(payload, "manual_readbooks_roobyroo"),
			"Manual_ReadBooks_RoobyRoo",
		)

	def test_manual_data_game_json_full_discover(self) -> None:
		buffer = io.BytesIO()
		with zipfile.ZipFile(buffer, "w") as archive:
			archive.writestr(
				"manual_readbooks_roobyroo/data/game.json",
				'{"game": "ReadBooks", "creator": "RoobyRoo"}\n',
			)
			archive.writestr(
				"manual_readbooks_roobyroo/Items.py",
				'game = "Manual"\n',
			)
			archive.writestr(
				"manual_readbooks_roobyroo/ManualClient.py",
				'game = "not set"\n',
			)
			archive.writestr(
				"manual_readbooks_roobyroo/__init__.py",
				"class ManualWorld:\n\tpass\n",
			)
		payload = buffer.getvalue()
		url = (
			"https://github.com/Virunas/apworldcollection/releases/download/"
			"v3.0.0/manual_readbooks_roobyroo.apworld"
		)
		world = discover_from_release_url(url, archive_bytes=payload)
		self.assertEqual(world.apworld_id, "manual_readbooks_roobyroo")
		self.assertEqual(world.name, "Manual_ReadBooks_RoobyRoo")
		self.assertEqual(world.display_name, "Manual: ReadBooks")
		self.assertEqual(world.version, "3.0.0")
		toml = render_discovered_toml(world)
		self.assertIn('name = "Manual_ReadBooks_RoobyRoo"', toml)
		self.assertIn('display_name = "Manual: ReadBooks"', toml)

	def test_ignores_test_json_fragments_that_alias_game(self) -> None:
		"""Elden Ring 0.6.1 shipped tests with `game = manifest.get("game")` and
		`manifest = '{"screenshot":"' + digest`, which previously resolved to `{`."""
		buffer = io.BytesIO()
		with zipfile.ZipFile(buffer, "w") as archive:
			archive.writestr(
				"eldenring/__init__.py",
				"from .core import GreenfieldEldenRingWorld, GAME\n",
			)
			archive.writestr("eldenring/gamename.py", 'GAME = "Elden Ring"\n')
			archive.writestr(
				"eldenring/core.py",
				"from .gamename import GAME\n\n"
				"class GreenfieldEldenRingWorld:\n"
				"\tgame = GAME\n",
			)
			archive.writestr(
				"eldenring/archipelago.json",
				'{"game": "Elden Ring", "world_version": "0.6.1"}\n',
			)
			archive.writestr(
				"eldenring/tests/test_gf_apworld_manifest.py",
				'game = manifest.get("game")\n',
			)
			archive.writestr(
				"eldenring/tests/test_gf_evidence_ledger.py",
				"digest = 'sha256:' + 'a' * 64\n"
				"manifest = '{\"screenshot\":\"' + digest + '\"}'\n",
			)
		payload = buffer.getvalue()
		self.assertEqual(extract_game_name(payload, "eldenring"), "Elden Ring")

	def test_does_not_treat_attribute_access_as_a_constant(self) -> None:
		buffer = io.BytesIO()
		with zipfile.ZipFile(buffer, "w") as archive:
			archive.writestr(
				"demo/__init__.py",
				"class DemoWorld:\n"
				"\tgame = GAME_NAME\n"
				"\tother = manifest.get('game')\n",
			)
			archive.writestr("demo/names.py", 'GAME_NAME = "Demo Game"\n')
			archive.writestr(
				"demo/helpers.py",
				"manifest = '{\"game\":\"Nope\"}'\n"
				"game = manifest.get(\"game\")\n",
			)
		payload = buffer.getvalue()
		self.assertEqual(extract_game_name(payload, "demo"), "Demo Game")

	def test_ambiguous_python_falls_back_to_manifest(self) -> None:
		buffer = io.BytesIO()
		with zipfile.ZipFile(buffer, "w") as archive:
			archive.writestr("demo/__init__.py", "from .core import DemoWorld\n")
			archive.writestr(
				"demo/core.py",
				'class DemoWorld:\n\tgame = "From Core"\n',
			)
			archive.writestr(
				"demo/other.py",
				'class Other:\n\tgame = "From Other"\n',
			)
			archive.writestr(
				"demo/archipelago.json",
				'{"game": "From Manifest"}\n',
			)
		payload = buffer.getvalue()
		self.assertEqual(extract_game_name(payload, "demo"), "From Manifest")


if __name__ == "__main__":
	unittest.main()
