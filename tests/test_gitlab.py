from __future__ import annotations

import io
import unittest
import zipfile
from unittest.mock import patch

from sylvanova_apworld_bot.discover import (
	DiscoveryError,
	discover_from_release_url,
	resolve_release_asset_url,
)
from sylvanova_apworld_bot.gitlab import (
	gitlab_hosts_from_env,
	parse_gitlab_direct_download_url,
	parse_gitlab_release_page_url,
	resolve_gitlab_url,
)
from sylvanova_apworld_bot.toml_template import render_discovered_toml


def _make_apworld(package: str, init_source: str) -> bytes:
	buffer = io.BytesIO()
	with zipfile.ZipFile(buffer, "w") as archive:
		archive.writestr(f"{package}/__init__.py", init_source)
	return buffer.getvalue()


class GitLabUrlParseTests(unittest.TestCase):
	def test_parse_direct_download(self) -> None:
		url = (
			"https://gitlab.com/acme/apworlds/-/releases/demo-1.2.3/downloads/demo.apworld"
		)
		asset = parse_gitlab_direct_download_url(url)
		self.assertIsNotNone(asset)
		assert asset is not None
		self.assertEqual(asset.host, "gitlab.com")
		self.assertEqual(asset.project_path, "acme/apworlds")
		self.assertEqual(asset.tag, "demo-1.2.3")
		self.assertEqual(asset.asset, "demo.apworld")
		self.assertEqual(asset.home, "https://gitlab.com/acme/apworlds")

	def test_parse_release_page(self) -> None:
		parsed = parse_gitlab_release_page_url(
			"https://gitlab.com/acme/apworlds/-/releases/v2.0.0"
		)
		self.assertEqual(parsed, ("gitlab.com", "acme/apworlds", "v2.0.0"))

	def test_self_hosted_direct_download(self) -> None:
		url = (
			"https://git.example.com/games/demo/-/releases/1.0.0/downloads/demo.apworld"
		)
		asset = parse_gitlab_direct_download_url(url)
		self.assertIsNotNone(asset)
		assert asset is not None
		self.assertEqual(asset.host, "git.example.com")


class GitLabResolveTests(unittest.TestCase):
	def test_release_page_fetches_single_apworld(self) -> None:
		release_payload = {
			"tag_name": "demo-1.2.3",
			"assets": {
				"links": [
					{
						"name": "demo.apworld",
						"direct_asset_url": (
							"https://gitlab.com/acme/apworlds/-/releases/demo-1.2.3/"
							"downloads/demo.apworld"
						),
					}
				]
			},
		}
		with patch(
			"sylvanova_apworld_bot.gitlab._gitlab_api_request",
			return_value=__import__("json").dumps(release_payload).encode(),
		) as api:
			asset = resolve_gitlab_url(
				"https://gitlab.com/acme/apworlds/-/releases/demo-1.2.3",
				token=None,
			)
			api.assert_called_once()
			self.assertEqual(asset.tag, "demo-1.2.3")
			self.assertEqual(asset.asset, "demo.apworld")

	def test_project_url_uses_latest_release(self) -> None:
		list_payload = [
			{
				"tag_name": "demo-2.0.0",
				"assets": {
					"links": [
						{
							"name": "demo.apworld",
							"url": (
								"https://gitlab.com/acme/apworlds/-/releases/demo-2.0.0/"
								"downloads/demo.apworld"
							),
						}
					]
				},
			},
		]
		with patch(
			"sylvanova_apworld_bot.gitlab._gitlab_api_request",
			return_value=__import__("json").dumps(list_payload).encode(),
		):
			asset = resolve_gitlab_url(
				"https://gitlab.com/acme/apworlds",
				token="secret",
			)
			self.assertEqual(asset.tag, "demo-2.0.0")

	def test_multiple_apworlds_rejected(self) -> None:
		release_payload = {
			"tag_name": "multi",
			"assets": {
				"links": [
					{"name": "a.apworld", "direct_asset_url": "https://gitlab.com/x/a.apworld"},
					{"name": "b.apworld", "direct_asset_url": "https://gitlab.com/x/b.apworld"},
				]
			},
		}
		with patch(
			"sylvanova_apworld_bot.gitlab._gitlab_api_request",
			return_value=__import__("json").dumps(release_payload).encode(),
		):
			with self.assertRaises(DiscoveryError) as ctx:
				resolve_gitlab_url(
					"https://gitlab.com/acme/apworlds/-/releases/multi",
					token=None,
				)
			self.assertIn("multiple", str(ctx.exception).lower())

	def test_custom_host_requires_gitlab_hosts(self) -> None:
		with self.assertRaises(DiscoveryError):
			resolve_gitlab_url(
				"https://git.example.com/acme/demo",
				token=None,
				known_hosts=gitlab_hosts_from_env(""),
			)


class GitLabDiscoverIntegrationTests(unittest.TestCase):
	def test_full_discover_direct_link(self) -> None:
		payload = _make_apworld("demo", 'game = "Demo Game"\n')
		url = (
			"https://gitlab.com/acme/apworlds/-/releases/demo-1.2.3/downloads/demo.apworld"
		)
		world = discover_from_release_url(url, archive_bytes=payload)
		self.assertEqual(world.apworld_id, "demo")
		self.assertEqual(world.version, "1.2.3")
		self.assertEqual(world.home, "https://gitlab.com/acme/apworlds")
		self.assertTrue(world.uses_default_url)
		self.assertIn("/-/releases/demo-{{version}}/downloads/", world.url_or_template)
		toml = render_discovered_toml(world)
		self.assertIn('home = "https://gitlab.com/acme/apworlds"', toml)

	def test_resolve_release_asset_url_gitlab(self) -> None:
		url = (
			"https://gitlab.com/acme/apworlds/-/releases/v1.0.0/downloads/demo.apworld"
		)
		home, tag, asset, source = resolve_release_asset_url(url)
		self.assertEqual(home, "https://gitlab.com/acme/apworlds")
		self.assertEqual(tag, "v1.0.0")
		self.assertEqual(asset, "demo.apworld")
		self.assertEqual(source, url)


if __name__ == "__main__":
	unittest.main()
