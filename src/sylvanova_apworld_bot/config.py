from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

from .gitlab import gitlab_hosts_from_env


_DEFAULT_MAX_BYTES = 50 * 1024 * 1024


@dataclass(frozen=True)
class Settings:
	discord_token: str
	discord_guild_id: int
	github_token: str
	gitlab_token: str | None
	gitlab_hosts: frozenset[str]
	index_repo: str
	index_base_branch: str
	pr_branch_prefix: str
	apworld_max_bytes: int


def load_settings() -> Settings:
	load_dotenv()
	token = os.environ.get("DISCORD_TOKEN", "").strip()
	guild = os.environ.get("DISCORD_GUILD_ID", "").strip()
	github = os.environ.get("GITHUB_TOKEN", "").strip()
	if not token or not guild or not github:
		raise RuntimeError(
			"DISCORD_TOKEN, DISCORD_GUILD_ID, and GITHUB_TOKEN are required "
			"(see .env.example)"
		)
	max_bytes_raw = os.environ.get("APWORLD_MAX_BYTES", "").strip()
	apworld_max_bytes = int(max_bytes_raw) if max_bytes_raw else _DEFAULT_MAX_BYTES
	gitlab_token_raw = os.environ.get("GITLAB_TOKEN", "").strip()
	gitlab_token = gitlab_token_raw or None
	gitlab_hosts = gitlab_hosts_from_env(os.environ.get("GITLAB_HOSTS", ""))
	return Settings(
		discord_token=token,
		discord_guild_id=int(guild),
		github_token=github,
		gitlab_token=gitlab_token,
		gitlab_hosts=gitlab_hosts,
		index_repo=os.environ.get("INDEX_REPO", "SylvaNova-Developers/SylvaNova-Archipelago-Index").strip(),
		index_base_branch=os.environ.get("INDEX_BASE_BRANCH", "main").strip(),
		pr_branch_prefix=os.environ.get("PR_BRANCH_PREFIX", "bot/apworld-").strip(),
		apworld_max_bytes=apworld_max_bytes,
	)
