from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from github import Github, GithubException
from github.Repository import Repository

if TYPE_CHECKING:
	from .discover import DiscoveredWorld


@dataclass(frozen=True)
class OpenedPullRequest:
	number: int
	url: str
	branch: str


@dataclass(frozen=True)
class ExistingApworldFile:
	path: str
	content: str
	sha: str


class IndexPullRequestClient:
	def __init__(self, *, token: str, repo_full_name: str, base_branch: str, branch_prefix: str):
		self._gh = Github(token)
		self._repo: Repository = self._gh.get_repo(repo_full_name)
		self._base_branch = base_branch
		self._branch_prefix = branch_prefix

	def apworld_exists(self, apworld: str) -> bool:
		return self._path_exists_on_base(f"index/{apworld}.toml")

	def get_apworld_toml(self, apworld: str) -> ExistingApworldFile | None:
		path = f"index/{apworld}.toml"
		try:
			contents = self._repo.get_contents(path, ref=self._base_branch)
		except GithubException as exc:
			if exc.status == 404:
				return None
			raise
		if isinstance(contents, list):
			raise RuntimeError(f"Expected a file at `{path}`, found a directory")
		raw = contents.decoded_content
		text = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
		return ExistingApworldFile(path=path, content=text, sha=contents.sha)

	def open_apworld_pr(
		self,
		*,
		apworld: str,
		toml_body: str,
		requested_by: str,
		world: DiscoveredWorld | None = None,
		is_update: bool = False,
	) -> OpenedPullRequest:
		path = f"index/{apworld}.toml"
		exists_on_base = self._path_exists_on_base(path)
		if is_update and not exists_on_base:
			raise RuntimeError(f"`{path}` does not exist on {self._base_branch}")
		if not is_update and exists_on_base:
			raise RuntimeError(f"`{path}` already exists on {self._base_branch}")

		base_ref = self._repo.get_git_ref(f"heads/{self._base_branch}")
		base_sha = base_ref.object.sha
		branch = f"{self._branch_prefix}{apworld}"
		self._ensure_branch(branch, base_sha, wipe_index_file=not is_update)

		if is_update:
			contents = self._repo.get_contents(path, ref=branch)
			if isinstance(contents, list):
				raise RuntimeError(f"Expected a file at `{path}`, found a directory")
			self._repo.update_file(
				path=path,
				message=f"Update {apworld} apworld via Discord request",
				content=toml_body,
				sha=contents.sha,
				branch=branch,
			)
			title = f"Update {apworld}"
		else:
			self._repo.create_file(
				path=path,
				message=f"Add {apworld} apworld via Discord request",
				content=toml_body,
				branch=branch,
			)
			title = f"Add {apworld}"

		body = self._build_pr_body(
			path=path,
			requested_by=requested_by,
			world=world,
			is_update=is_update,
		)
		pr = self._repo.create_pull(
			title=title,
			body=body,
			head=branch,
			base=self._base_branch,
		)
		return OpenedPullRequest(number=pr.number, url=pr.html_url, branch=branch)

	def _build_pr_body(
		self,
		*,
		path: str,
		requested_by: str,
		world: DiscoveredWorld | None,
		is_update: bool = False,
	) -> str:
		action = "update" if is_update else "request"
		lines = [
			f"Automated apworld {action} from Discord user `{requested_by}`.",
			"",
			f"- File: `{path}`",
		]
		if is_update:
			lines.append("- Mode: add/update version on an existing index entry")
			lines.append(
				"- Note: `Manual_*` index entries are separate worlds and do not block "
				"non-manual apworld ids."
			)
		if world is not None:
			lines.extend(
				[
					f"- Apworld id: `{world.apworld_id}`",
					f"- Game name: `{world.name}`",
					f"- Version: `{world.version}`",
					f"- Home: {world.home}",
					f"- Source: {world.source_url}",
				]
			)
			if world.uses_default_url:
				lines.append(f"- default_url: `{world.url_or_template}`")
		lines.extend(
			[
				"",
				"Opened by SylvaNova-apworld-bot.",
				"",
				"Index `PR CI` will validate, fuzz, and auto-merge when green.",
			]
		)
		return "\n".join(lines)

	def _path_exists_on_base(self, path: str) -> bool:
		try:
			self._repo.get_contents(path, ref=self._base_branch)
			return True
		except GithubException as exc:
			if exc.status == 404:
				return False
			raise

	def _ensure_branch(self, branch: str, base_sha: str, *, wipe_index_file: bool) -> None:
		ref_name = f"refs/heads/{branch}"
		try:
			self._repo.create_git_ref(ref=ref_name, sha=base_sha)
		except GithubException as exc:
			if exc.status != 422:
				raise
			# Branch already exists — move it to current base so retries are clean.
			ref = self._repo.get_git_ref(f"heads/{branch}")
			ref.edit(base_sha, force=True)
			if not wipe_index_file:
				return
			try:
				existing = self._repo.get_contents(
					f"index/{branch.removeprefix(self._branch_prefix)}.toml",
					ref=branch,
				)
				# If a previous add attempt left a file, delete so create_file can succeed.
				if not isinstance(existing, list):
					self._repo.delete_file(
						path=existing.path,
						message=f"Reset {existing.path} before re-opening request PR",
						sha=existing.sha,
						branch=branch,
					)
			except GithubException as inner:
				if inner.status != 404:
					raise
