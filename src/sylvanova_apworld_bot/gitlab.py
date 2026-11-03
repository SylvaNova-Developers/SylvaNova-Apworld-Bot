from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from .discover import DiscoveryError

_USER_AGENT = "SylvaNova-apworld-bot/0.1 (+https://github.com/SylvaNova-Developers/SylvaNova-Archipelago-Index)"


@dataclass(frozen=True)
class GitLabReleaseAsset:
	host: str
	project_path: str
	tag: str
	asset: str
	url: str

	@property
	def home(self) -> str:
		return f"https://{self.host}/{self.project_path}"


def gitlab_hosts_from_env(raw: str | None) -> frozenset[str]:
	"""Hosts treated as GitLab when resolving bare project URLs (no `/-/` in path)."""
	hosts = {"gitlab.com"}
	if raw:
		for part in raw.split(","):
			value = part.strip().lower()
			if value:
				hosts.add(value)
	return frozenset(hosts)


def is_gitlab_release_url(url: str) -> bool:
	parsed = urlparse(url.strip())
	if parsed.scheme != "https" or not parsed.netloc:
		return False
	path = parsed.path
	return "/-/releases/" in path


def is_gitlab_project_url(url: str, *, known_hosts: frozenset[str]) -> bool:
	parsed = urlparse(url.strip())
	if parsed.scheme != "https" or not parsed.netloc:
		return False
	if "/-/" in parsed.path:
		return False
	host = parsed.netloc.lower()
	if host not in known_hosts:
		return False
	segments = [segment for segment in parsed.path.strip("/").split("/") if segment]
	return len(segments) >= 2


def _split_gitlab_project_and_suffix(path: str) -> tuple[str, str | None]:
	"""Return (project_path, remainder after `/-/`) from a GitLab web path."""
	clean = path.strip("/")
	if "/-/" not in clean:
		return clean, None
	project, suffix = clean.split("/-/", 1)
	return project, suffix


def parse_gitlab_direct_download_url(url: str) -> GitLabReleaseAsset | None:
	parsed = urlparse(url.strip().split("?")[0])
	if parsed.scheme != "https" or not parsed.netloc:
		return None
	project_path, suffix = _split_gitlab_project_and_suffix(parsed.path)
	if suffix is None:
		return None
	parts = suffix.strip("/").split("/")
	if len(parts) < 4 or parts[0] != "releases" or parts[2] != "downloads":
		return None
	tag = parts[1]
	filename = parts[3]
	if not filename.lower().endswith(".apworld"):
		return None
	from urllib.parse import unquote

	return GitLabReleaseAsset(
		host=parsed.netloc.lower(),
		project_path=project_path,
		tag=unquote(tag),
		asset=unquote(filename),
		url=parsed.geturl(),
	)


def parse_gitlab_release_page_url(url: str) -> tuple[str, str, str] | None:
	"""Return (host, project_path, tag) for a release page URL."""
	value = url.strip().split("?")[0].rstrip("/")
	parsed = urlparse(value)
	if parsed.scheme != "https" or not parsed.netloc:
		return None
	project_path, suffix = _split_gitlab_project_and_suffix(parsed.path)
	if suffix is None:
		return None
	parts = suffix.strip("/").split("/")
	if len(parts) != 2 or parts[0] != "releases":
		return None
	from urllib.parse import unquote

	tag = unquote(parts[1])
	if tag.lower() == "permalink":
		return None
	return parsed.netloc.lower(), project_path, tag


def parse_gitlab_project_url(url: str, *, known_hosts: frozenset[str]) -> tuple[str, str] | None:
	value = url.strip().split("?")[0].rstrip("/")
	if not is_gitlab_project_url(value, known_hosts=known_hosts):
		return None
	parsed = urlparse(value)
	project_path = parsed.path.strip("/")
	return parsed.netloc.lower(), project_path


def _gitlab_api_request(
	host: str,
	api_path: str,
	*,
	token: str | None,
	timeout: int = 60,
) -> bytes:
	url = f"https://{host}/api/v4{api_path}"
	headers = {"User-Agent": _USER_AGENT, "Accept": "application/json"}
	if token:
		headers["PRIVATE-TOKEN"] = token.strip()
	request = Request(url, headers=headers)
	try:
		with urlopen(request, timeout=timeout) as response:
			return response.read()
	except HTTPError as exc:
		if exc.code == 404:
			raise DiscoveryError("GitLab project or release was not found (HTTP 404).") from exc
		if exc.code in {401, 403}:
			hint = " Set GITLAB_TOKEN if the project is private." if not token else ""
			raise DiscoveryError(
				f"GitLab API rejected the request (HTTP {exc.code}).{hint}"
			) from exc
		raise DiscoveryError(f"GitLab API request failed (HTTP {exc.code}).") from exc
	except URLError as exc:
		raise DiscoveryError(f"GitLab API request failed: {exc.reason}") from exc


def _encoded_project_path(project_path: str) -> str:
	return quote(project_path, safe="")


def _fetch_release(host: str, project_path: str, tag: str, *, token: str | None) -> dict:
	encoded_project = _encoded_project_path(project_path)
	encoded_tag = quote(tag, safe="")
	raw = _gitlab_api_request(
		host,
		f"/projects/{encoded_project}/releases/{encoded_tag}",
		token=token,
	)
	try:
		data = json.loads(raw.decode("utf-8"))
	except json.JSONDecodeError as exc:
		raise DiscoveryError("GitLab API returned invalid JSON for the release.") from exc
	if not isinstance(data, dict):
		raise DiscoveryError("GitLab API returned an unexpected release payload.")
	return data


def _fetch_releases(host: str, project_path: str, *, token: str | None) -> list[dict]:
	encoded_project = _encoded_project_path(project_path)
	raw = _gitlab_api_request(
		host,
		f"/projects/{encoded_project}/releases?per_page=20&order_by=released_at&sort=desc",
		token=token,
	)
	try:
		data = json.loads(raw.decode("utf-8"))
	except json.JSONDecodeError as exc:
		raise DiscoveryError("GitLab API returned invalid JSON for releases.") from exc
	if not isinstance(data, list) or not data:
		raise DiscoveryError(
			"No GitLab releases were found for this project. Publish a release with a `.apworld` asset first."
		)
	releases: list[dict] = []
	for entry in data:
		if isinstance(entry, dict):
			releases.append(entry)
	if not releases:
		raise DiscoveryError(
			"No GitLab releases were found for this project. Publish a release with a `.apworld` asset first."
		)
	return releases


def _fetch_latest_release(host: str, project_path: str, *, token: str | None) -> dict:
	return _fetch_releases(host, project_path, token=token)[0]


def _apworld_links_from_release(release: dict) -> list[tuple[str, str, str]]:
	"""Return list of (name, direct_url, tag) for .apworld release link assets."""
	tag = str(release.get("tag_name", "")).strip()
	if not tag:
		raise DiscoveryError("GitLab release is missing `tag_name`.")
	assets = release.get("assets")
	if not isinstance(assets, dict):
		return []
	links = assets.get("links")
	if not isinstance(links, list):
		return []
	found: list[tuple[str, str, str]] = []
	for entry in links:
		if not isinstance(entry, dict):
			continue
		name = str(entry.get("name", "")).strip()
		direct = entry.get("direct_asset_url") or entry.get("url")
		if not isinstance(direct, str) or not direct.strip():
			continue
		direct = direct.strip().split("?")[0]
		if name.lower().endswith(".apworld") or direct.lower().endswith(".apworld"):
			asset_name = name if name.lower().endswith(".apworld") else direct.rsplit("/", 1)[-1]
			found.append((asset_name, direct, tag))
	return found


def _asset_from_release(
	host: str,
	project_path: str,
	release: dict,
) -> GitLabReleaseAsset:
	candidates = _apworld_links_from_release(release)
	if not candidates:
		raise DiscoveryError(
			"GitLab release has no `.apworld` link asset. "
			"Add the apworld to the release assets, or paste a direct "
			"`/-/releases/<tag>/downloads/<file>.apworld` link."
		)
	if len(candidates) > 1:
		names = ", ".join(sorted(name for name, _, _ in candidates))
		raise DiscoveryError(
			"GitLab release has multiple `.apworld` assets "
			f"({names}). Submit a direct download link for the file you want indexed."
		)
	name, direct_url, tag = candidates[0]
	return GitLabReleaseAsset(
		host=host,
		project_path=project_path,
		tag=tag,
		asset=name,
		url=direct_url,
	)


def resolve_gitlab_url(
	url: str,
	*,
	token: str | None,
	known_hosts: frozenset[str] | None = None,
) -> GitLabReleaseAsset:
	value = url.strip()
	hosts = known_hosts if known_hosts is not None else gitlab_hosts_from_env(None)

	direct = parse_gitlab_direct_download_url(value)
	if direct is not None:
		return direct

	release_page = parse_gitlab_release_page_url(value)
	if release_page is not None:
		host, project_path, tag = release_page
		release = _fetch_release(host, project_path, tag, token=token)
		return _asset_from_release(host, project_path, release)

	project = parse_gitlab_project_url(value, known_hosts=hosts)
	if project is not None:
		host, project_path = project
		last_error: DiscoveryError | None = None
		for release in _fetch_releases(host, project_path, token=token):
			try:
				return _asset_from_release(host, project_path, release)
			except DiscoveryError as exc:
				last_error = exc
		if last_error is not None:
			raise last_error
		raise DiscoveryError(
			"No GitLab release with a `.apworld` link asset was found for this project."
		)

	raise DiscoveryError(
		"URL is not a recognized GitLab project, release, or direct "
		"`.apworld` download link. Use `https://gitlab.com/group/project`, "
		"a `/-/releases/<tag>` page, or a "
		"`/-/releases/<tag>/downloads/<file>.apworld` link."
	)
