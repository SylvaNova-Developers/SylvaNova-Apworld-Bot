from __future__ import annotations

import unittest

from sylvanova_apworld_bot.discover import DiscoveredWorld
from sylvanova_apworld_bot.toml_template import (
	TomlMergeError,
	merge_discovered_version,
	parse_index_world_toml,
)


def _world(**overrides: object) -> DiscoveredWorld:
	base = dict(
		apworld_id="pokemon_bw",
		name="Pokemon Black and White",
		version="0.3.37",
		home="https://github.com/BlastSlimey/PokemonBWAP",
		source_url=(
			"https://github.com/BlastSlimey/PokemonBWAP/releases/download/"
			"0.3.37/pokemon_bw.apworld"
		),
		url_or_template=(
			"https://github.com/BlastSlimey/PokemonBWAP/releases/download/"
			"{{version}}/pokemon_bw.apworld"
		),
		display_name=None,
		uses_default_url=True,
	)
	base.update(overrides)
	return DiscoveredWorld(**base)  # type: ignore[arg-type]


class TomlMergeTests(unittest.TestCase):
	def test_append_version_same_default_url(self) -> None:
		existing = parse_index_world_toml(
			"""
name = "Demo Game"
home = "https://github.com/acme/demo"
default_url = "https://github.com/acme/demo/releases/download/{{version}}/demo.apworld"

[versions]
"1.0.0" = {}
""".strip()
			+ "\n"
		)
		world = _world(
			apworld_id="demo",
			name="Demo Game",
			version="1.1.0",
			home="https://github.com/acme/demo",
			source_url="https://github.com/acme/demo/releases/download/1.1.0/demo.apworld",
			url_or_template=(
				"https://github.com/acme/demo/releases/download/{{version}}/demo.apworld"
			),
		)
		merged = merge_discovered_version(existing, world)
		self.assertIn('"1.0.0" = {}', merged)
		self.assertIn('"1.1.0" = {}', merged)
		self.assertNotIn("disabled", merged)

	def test_default_url_change_pins_old_versions(self) -> None:
		existing = parse_index_world_toml(
			"""
name = "Pokemon Black and White"
home = "https://discord.com/channels/example"
default_url = "https://github.com/BlastSlimey/PokemonBWAP/releases/download/{{version}}/pokemon_bw_without_maps.apworld"
disabled = true

[versions]
"0.3.17" = {}
"0.3.14" = {}
""".strip()
			+ "\n"
		)
		merged = merge_discovered_version(existing, _world())
		self.assertIn(
			'default_url = "https://github.com/BlastSlimey/PokemonBWAP/releases/download/{{version}}/pokemon_bw.apworld"',
			merged,
		)
		self.assertIn(
			'"0.3.17" = { url = "https://github.com/BlastSlimey/PokemonBWAP/releases/download/0.3.17/pokemon_bw_without_maps.apworld" }',
			merged,
		)
		self.assertIn(
			'"0.3.14" = { url = "https://github.com/BlastSlimey/PokemonBWAP/releases/download/0.3.14/pokemon_bw_without_maps.apworld" }',
			merged,
		)
		self.assertIn('"0.3.37" = {}', merged)
		self.assertNotIn("disabled", merged)

	def test_rejects_duplicate_version(self) -> None:
		existing = parse_index_world_toml(
			"""
name = "Demo Game"
default_url = "https://github.com/acme/demo/releases/download/{{version}}/demo.apworld"

[versions]
"1.1.0" = {}
""".strip()
			+ "\n"
		)
		world = _world(
			apworld_id="demo",
			name="Demo Game",
			version="1.1.0",
			url_or_template=(
				"https://github.com/acme/demo/releases/download/{{version}}/demo.apworld"
			),
		)
		with self.assertRaises(TomlMergeError) as ctx:
			merge_discovered_version(existing, world)
		self.assertIn("already listed", str(ctx.exception))

	def test_manual_sibling_is_irrelevant_to_parse(self) -> None:
		"""Manual tomls are different files; merge only sees the target apworld id."""
		existing = parse_index_world_toml(
			"""
name = "Pokemon Black and White"
default_url = "https://github.com/BlastSlimey/PokemonBWAP/releases/download/{{version}}/pokemon_bw.apworld"

[versions]
"0.3.17" = {}
""".strip()
			+ "\n"
		)
		# Presence of a Manual_* world elsewhere must not affect this merge.
		merged = merge_discovered_version(existing, _world())
		self.assertIn('"0.3.37" = {}', merged)
		self.assertNotIn("Manual_", merged)


if __name__ == "__main__":
	unittest.main()
