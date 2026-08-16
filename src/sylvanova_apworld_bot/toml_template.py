from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from .discover import DiscoveredWorld

_APWORLD_ID = re.compile(r"^[a-z0-9][a-z0-9_\-]*$")


def validate_apworld_id(apworld: str) -> str:
	value = apworld.strip()
	if not _APWORLD_ID.match(value):
		raise ValueError(
			"apworld id must be lowercase alphanumeric with optional _/- "
			f"(got {apworld!r})"
		)
	return value


@dataclass(frozen=True)
class ExistingIndexWorld:
	"""Parsed fields from an existing index/{apworld}.toml."""

	raw_toml: str
	name: str
	versions: dict[str, dict]
	display_name: str | None
	home: str | None
	default_url: str | None
	disabled: bool
	supported: bool
	tags: list[str]


class TomlMergeError(ValueError):
	"""User-facing failure while merging a discovered version into existing TOML."""


def parse_index_world_toml(raw_toml: str) -> ExistingIndexWorld:
	data = tomllib.loads(raw_toml)
	name = str(data.get("name", "")).strip()
	if not name:
		raise TomlMergeError("Existing index entry is missing required `name`.")

	versions_raw = data.get("versions")
	versions: dict[str, dict] = {}
	if isinstance(versions_raw, dict):
		for version, src in versions_raw.items():
			if src is None:
				versions[str(version)] = {}
			elif isinstance(src, dict):
				versions[str(version)] = dict(src)
			else:
				raise TomlMergeError(
					f"Existing index entry has invalid source for version {version!r}."
				)

	display_name = data.get("display_name")
	home = data.get("home")
	default_url = data.get("default_url")
	tags_raw = data.get("tags")
	tags = [str(tag) for tag in tags_raw] if isinstance(tags_raw, list) else []

	return ExistingIndexWorld(
		raw_toml=raw_toml,
		name=name,
		versions=versions,
		display_name=str(display_name) if display_name else None,
		home=str(home) if home else None,
		default_url=str(default_url) if default_url else None,
		disabled=data.get("disabled") is True,
		supported=data.get("supported") is True,
		tags=tags,
	)


def resolve_version_url(world: ExistingIndexWorld, version: str) -> str | None:
	src = world.versions.get(version)
	if src is None:
		return None
	if "url" in src and isinstance(src["url"], str):
		return src["url"]
	if "local" in src:
		return None
	if world.default_url:
		return world.default_url.replace("{{version}}", version)
	return None


def render_world_toml(
	*,
	name: str,
	url: str,
	version: str,
	home: str | None = None,
	display_name: str | None = None,
) -> str:
	"""Build an index/{apworld}.toml body matching the index README format."""
	lines: list[str] = [f'name = "{_escape(name)}"']
	if display_name:
		lines.append(f'display_name = "{_escape(display_name)}"')
	if home:
		lines.append(f'home = "{_escape(home)}"')

	if "{{version}}" in url:
		lines.append(f'default_url = "{_escape(url)}"')
		lines.append("")
		lines.append("[versions]")
		lines.append(f'"{_escape(version)}" = {{}}')
	else:
		lines.append("")
		lines.append("[versions]")
		lines.append(f'"{_escape(version)}" = {{ url = "{_escape(url)}" }}')

	lines.append("")
	return "\n".join(lines)


def render_discovered_toml(world: DiscoveredWorld) -> str:
	return render_world_toml(
		name=world.name,
		url=world.url_or_template,
		version=world.version,
		home=world.home,
		display_name=world.display_name,
	)


def merge_discovered_version(existing: ExistingIndexWorld, world: DiscoveredWorld) -> str:
	"""Merge a newly discovered release into an existing index entry.

	Manual_* siblings are unrelated index keys and never participate here — only the
	exact apworld id's TOML is updated.

	When `default_url` changes, previous versions that relied on the old template are
	pinned to explicit URLs so historical downloads keep resolving.
	"""
	if existing.supported:
		raise TomlMergeError(
			"This apworld is marked supported=true in the index and cannot be "
			"updated via the Discord bot. Ask Chou or Virunas."
		)
	if world.version in existing.versions:
		raise TomlMergeError(
			f"Version {world.version!r} is already listed for this apworld."
		)

	name = world.name or existing.name
	display_name = world.display_name if world.display_name is not None else existing.display_name
	home = world.home or existing.home

	effective_default = (
		world.url_or_template if world.uses_default_url else existing.default_url
	)
	default_url_changed = (
		world.uses_default_url
		and existing.default_url is not None
		and world.url_or_template != existing.default_url
	)

	version_lines: list[str] = []
	for version in existing.versions:
		src = existing.versions[version]
		if "local" in src:
			raise TomlMergeError(
				f"Existing version {version!r} uses a local source; "
				"ask Chou or Virunas to migrate it before bot updates."
			)
		explicit_url = src.get("url") if isinstance(src.get("url"), str) else None
		if explicit_url:
			version_lines.append(
				f'"{_escape(version)}" = {{ url = "{_escape(explicit_url)}" }}'
			)
			continue
		if default_url_changed:
			pinned = resolve_version_url(existing, version)
			if not pinned:
				raise TomlMergeError(
					f"Could not resolve a download URL for existing version {version!r} "
					"while changing default_url."
				)
			version_lines.append(
				f'"{_escape(version)}" = {{ url = "{_escape(pinned)}" }}'
			)
			continue
		if existing.default_url:
			version_lines.append(f'"{_escape(version)}" = {{}}')
			continue
		pinned = resolve_version_url(existing, version)
		if not pinned:
			raise TomlMergeError(
				f"Could not resolve a download URL for existing version {version!r}."
			)
		version_lines.append(
			f'"{_escape(version)}" = {{ url = "{_escape(pinned)}" }}'
		)

	if world.uses_default_url:
		version_lines.append(f'"{_escape(world.version)}" = {{}}')
	else:
		version_lines.append(
			f'"{_escape(world.version)}" = {{ url = "{_escape(world.url_or_template)}" }}'
		)

	lines: list[str] = [f'name = "{_escape(name)}"']
	if display_name:
		lines.append(f'display_name = "{_escape(display_name)}"')
	if home:
		lines.append(f'home = "{_escape(home)}"')
	if existing.tags:
		tags = ", ".join(f'"{_escape(tag)}"' for tag in existing.tags)
		lines.append(f"tags = [{tags}]")
	# Intentionally clear disabled — a Discord request for a new version is a request
	# to host that release; index CI still has to pass before merge.
	if effective_default:
		lines.append(f'default_url = "{_escape(effective_default)}"')
	lines.append("")
	lines.append("[versions]")
	lines.extend(version_lines)
	lines.append("")
	return "\n".join(lines)


def _escape(value: str) -> str:
	return value.replace("\\", "\\\\").replace('"', '\\"')
