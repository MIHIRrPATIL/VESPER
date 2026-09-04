"""VESPER GitHub Specialist Agent.

Provides deep code intelligence and repository navigation:
  - Repository inspection (stars, forks, languages, branches).
  - Code search and symbol lookup across repositories.
  - File retrieval and line-range code snippet extraction.
  - Developer doubt solving and code explanation with repo context.
  - Issues, pull requests, and recent commit triage.
"""

from __future__ import annotations

import base64
import logging
from typing import Any, Dict, List, Optional
import httpx

from backend.agent.llm import LLMClient
from backend.agent.specialists.base import BaseSpecialist, SpecialistResult
from backend.shared.config import GITHUB_TOKEN

logger = logging.getLogger("vesper.agent.specialists.github")

DEFAULT_REPO = "MIHIRrPATIL/VESPER"


class GitHubSpecialist(BaseSpecialist):
    """Specialist sub-agent for GitHub code exploration, doubt solving, and repo triage."""

    def __init__(
        self,
        token: Optional[str] = None,
        llm_client: Optional[LLMClient] = None,
    ) -> None:
        self.token = token or GITHUB_TOKEN
        self.llm = llm_client or LLMClient()

    @property
    def name(self) -> str:
        return "github"

    @property
    def description(self) -> str:
        return (
            "Interacts with GitHub to fetch code snippets, explain code/solve doubts, "
            "search files, inspect repository info, and triage issues/commits."
        )

    def get_capabilities(self) -> str:
        return (
            "Search repositories and code, read code files and snippets, explain code and solve "
            "programming doubts, view open issues/PRs, and review recent commit activity."
        )

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "get_repo_info",
                "description": "Retrieves metadata, description, primary language, stars, and open issues for a GitHub repository.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "repo": {
                            "type": "string",
                            "description": "Repository identifier in 'owner/repo' format (e.g. 'MIHIRrPATIL/VESPER'). Defaults to primary project repo.",
                        },
                    },
                },
            },
            {
                "name": "search_code",
                "description": "Searches for code symbols, functions, classes, or patterns across a repository.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query (e.g. 'get_best_input_device', 'WakeWordDetector')."},
                        "repo": {"type": "string", "description": "Optional repository filter ('owner/repo'). Defaults to current project."},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "get_code_snippet",
                "description": "Retrieves file contents or a specific line range from a repository file.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Path to the file inside the repo (e.g. 'backend/voice/audio_utils.py')."},
                        "repo": {"type": "string", "description": "Repository identifier ('owner/repo'). Defaults to project repo."},
                        "start_line": {"type": "integer", "description": "Optional 1-indexed starting line number."},
                        "end_line": {"type": "integer", "description": "Optional 1-indexed ending line number."},
                        "ref": {"type": "string", "description": "Branch, tag, or commit hash (default 'main')."},
                    },
                    "required": ["path"],
                },
            },
            {
                "name": "solve_doubt",
                "description": "Answers a programming question, solves developer doubts, or explains code architecture with repository context.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "The coding question, doubt, or error message to explain/solve."},
                        "path": {"type": "string", "description": "Optional file path in the repo to reference for context."},
                        "code": {"type": "string", "description": "Optional code snippet to analyze."},
                        "repo": {"type": "string", "description": "Repository context ('owner/repo')."},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "list_issues",
                "description": "Lists recent issues or pull requests on a repository.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "repo": {"type": "string", "description": "Repository identifier ('owner/repo')."},
                        "state": {"type": "string", "enum": ["open", "closed", "all"], "description": "Issue state filter."},
                        "limit": {"type": "integer", "description": "Max issues to return (default 5)."},
                    },
                },
            },
            {
                "name": "get_recent_commits",
                "description": "Retrieves recent commits from the repository history.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "repo": {"type": "string", "description": "Repository identifier ('owner/repo')."},
                        "limit": {"type": "integer", "description": "Number of recent commits to fetch (default 5)."},
                    },
                },
            },
            {
                "name": "list_user_repos",
                "description": "Lists the authenticated user's recent GitHub repositories (e.g. 'what are my projects', 'my recent repos', 'what was my latest project on github').",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "Number of repos to fetch (default 5)."},
                        "sort": {"type": "string", "enum": ["pushed", "updated", "created", "full_name"], "description": "Sort order (default 'pushed' = most recently active)."},
                    },
                },
            },
        ]

    def _get_headers(self) -> Dict[str, str]:
        headers = {"Accept": "application/vnd.github.v3+json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _normalize_repo(self, repo: Optional[str]) -> str:
        if not repo or repo.strip() in ["", "current", "this", "vesper"]:
            return DEFAULT_REPO
        clean = repo.strip()
        if "/" not in clean:
            return f"MIHIRrPATIL/{clean}"
        return clean

    # ── Tool Implementations ─────────────────────────────────────────────────

    async def get_repo_info(self, repo: Optional[str] = None) -> SpecialistResult:
        """Fetches repository metadata from GitHub API."""
        target_repo = self._normalize_repo(repo)
        url = f"https://api.github.com/repos/{target_repo}"

        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.get(url, headers=self._get_headers())
                if res.status_code == 404:
                    return SpecialistResult(success=False, action="get_repo_info", error=f"Repository '{target_repo}' not found on GitHub.")
                if res.status_code != 200:
                    return SpecialistResult(success=False, action="get_repo_info", error=f"GitHub API returned HTTP {res.status_code}: {res.text}")

                data = res.json()
                name = data.get("full_name", target_repo)
                description = data.get("description") or "No description provided."
                stars = data.get("stargazers_count", 0)
                forks = data.get("forks_count", 0)
                open_issues = data.get("open_issues_count", 0)
                primary_lang = data.get("language") or "Mixed"
                default_branch = data.get("default_branch", "main")
                html_url = data.get("html_url", "")

                speech = (
                    f"Repository '{name}' is primarily written in {primary_lang}, with {stars} stars, "
                    f"{forks} forks, and {open_issues} open issues on branch '{default_branch}', sir."
                )

                return SpecialistResult(
                    success=True,
                    action="get_repo_info",
                    data={
                        "repo": name,
                        "description": description,
                        "stars": stars,
                        "forks": forks,
                        "open_issues": open_issues,
                        "language": primary_lang,
                        "default_branch": default_branch,
                        "url": html_url,
                    },
                    speech_summary=speech,
                    card_payload={
                        "type": "github_repo_card",
                        "title": name,
                        "description": description,
                        "stars": stars,
                        "forks": forks,
                        "language": primary_lang,
                        "url": html_url,
                    },
                )
        except Exception as e:
            logger.exception(f"[GitHubSpecialist] Error getting repo info: {e}")
            return SpecialistResult(success=False, action="get_repo_info", error=str(e))

    async def search_code(self, query: str, repo: Optional[str] = None) -> SpecialistResult:
        """Searches code inside a target repository or across GitHub."""
        target_repo = self._normalize_repo(repo)
        q = f"{query} repo:{target_repo}" if target_repo else query
        url = "https://api.github.com/search/code"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(url, headers=self._get_headers(), params={"q": q, "per_page": 5})
                if res.status_code != 200:
                    return SpecialistResult(success=False, action="search_code", error=f"Code search error (HTTP {res.status_code}): {res.text}")

                items = res.json().get("items", [])
                if not items:
                    return SpecialistResult(
                        success=True,
                        action="search_code",
                        data={"matches": [], "query": query},
                        speech_summary=f"No matching code references found for '{query}' in {target_repo}, sir.",
                    )

                matches = []
                for item in items[:5]:
                    matches.append({
                        "name": item.get("name"),
                        "path": item.get("path"),
                        "html_url": item.get("html_url"),
                        "repo": item.get("repository", {}).get("full_name"),
                    })

                file_list = ", ".join([m["path"] for m in matches[:3]])
                speech = f"Found {len(matches)} code references for '{query}' in {target_repo}, including {file_list}."

                return SpecialistResult(
                    success=True,
                    action="search_code",
                    data={"matches": matches, "query": query, "repo": target_repo},
                    speech_summary=speech,
                    card_payload={"type": "github_code_search_card", "query": query, "matches": matches},
                )
        except Exception as e:
            logger.exception(f"[GitHubSpecialist] Search code failed: {e}")
            return SpecialistResult(success=False, action="search_code", error=str(e))

    async def get_code_snippet(
        self,
        path: str,
        repo: Optional[str] = None,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
        ref: Optional[str] = None,
    ) -> SpecialistResult:
        """Fetches file contents or line slice from GitHub repository."""
        target_repo = self._normalize_repo(repo)
        url = f"https://api.github.com/repos/{target_repo}/contents/{path}"
        params = {}
        if ref:
            params["ref"] = ref

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(url, headers=self._get_headers(), params=params)
                if res.status_code == 404:
                    return SpecialistResult(success=False, action="get_code_snippet", error=f"File '{path}' not found in {target_repo}.")
                if res.status_code != 200:
                    return SpecialistResult(success=False, action="get_code_snippet", error=f"GitHub API error (HTTP {res.status_code})")

                file_data = res.json()
                raw_content = file_data.get("content", "")
                encoding = file_data.get("encoding", "base64")

                if encoding == "base64":
                    decoded_text = base64.b64decode(raw_content).decode("utf-8", errors="replace")
                else:
                    decoded_text = raw_content

                lines = decoded_text.splitlines()
                total_lines = len(lines)

                # Slice lines if requested
                s_line = max(1, start_line) if start_line else 1
                e_line = min(total_lines, end_line) if end_line else total_lines
                sliced_lines = lines[s_line - 1 : e_line]
                snippet = "\n".join(sliced_lines)

                speech = f"Retrieved lines {s_line} to {e_line} of '{path}' from {target_repo}, sir."

                return SpecialistResult(
                    success=True,
                    action="get_code_snippet",
                    data={
                        "path": path,
                        "repo": target_repo,
                        "start_line": s_line,
                        "end_line": e_line,
                        "total_lines": total_lines,
                        "content": snippet,
                        "url": file_data.get("html_url"),
                    },
                    speech_summary=speech,
                    card_payload={
                        "type": "github_snippet_card",
                        "path": path,
                        "repo": target_repo,
                        "lines": f"L{s_line}-L{e_line}",
                        "code": snippet,
                    },
                )
        except Exception as e:
            logger.exception(f"[GitHubSpecialist] Error fetching snippet: {e}")
            return SpecialistResult(success=False, action="get_code_snippet", error=str(e))

    async def solve_doubt(
        self,
        query: str,
        path: Optional[str] = None,
        code: Optional[str] = None,
        repo: Optional[str] = None,
    ) -> SpecialistResult:
        """Solves developer doubts with repository context using Alfred's reasoning."""
        context_code = code or ""
        target_repo = self._normalize_repo(repo)

        # If a path was provided without explicit code, fetch file snippet
        if path and not context_code:
            fetch_res = await self.get_code_snippet(path=path, repo=target_repo)
            if fetch_res.success:
                context_code = fetch_res.data.get("content", "")

        system_prompt = (
            "You are Alfred's Senior Software Engineering Specialist. "
            "Answer the developer's question or solve their code doubt with technical precision. "
            "Explain the core concept, diagnose any errors, and provide a clean code example if needed. "
            "Keep the response authoritative, concise, and direct."
        )

        user_content = f"Question/Doubt: {query}\n"
        if target_repo:
            user_content += f"Repository: {target_repo}\n"
        if path:
            user_content += f"File: {path}\n"
        if context_code:
            user_content += f"\nCode Context:\n```\n{context_code[:3000]}\n```\n"

        try:
            explanation, _ = await self.llm.generate_chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                max_tokens=650,
                temperature=0.2,
            )

            speech = f"I have analyzed the matter regarding {query}. {explanation.split('.')[0]}."

            return SpecialistResult(
                success=True,
                action="solve_doubt",
                data={"query": query, "solution": explanation, "repo": target_repo, "path": path},
                speech_summary=speech,
                card_payload={
                    "type": "github_doubt_solution",
                    "query": query,
                    "solution_markdown": explanation,
                },
            )
        except Exception as e:
            logger.exception(f"[GitHubSpecialist] Error solving doubt: {e}")
            return SpecialistResult(success=False, action="solve_doubt", error=str(e))

    async def list_issues(
        self,
        repo: Optional[str] = None,
        state: str = "open",
        limit: int = 5,
    ) -> SpecialistResult:
        """Lists issues/PRs for a repository."""
        target_repo = self._normalize_repo(repo)
        url = f"https://api.github.com/repos/{target_repo}/issues"
        params = {"state": state, "per_page": limit}

        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.get(url, headers=self._get_headers(), params=params)
                if res.status_code != 200:
                    return SpecialistResult(success=False, action="list_issues", error=f"GitHub API error (HTTP {res.status_code})")

                items = res.json()
                if not items:
                    return SpecialistResult(
                        success=True,
                        action="list_issues",
                        data={"issues": [], "repo": target_repo},
                        speech_summary=f"No {state} issues found in {target_repo}, sir.",
                    )

                issues = []
                for it in items[:limit]:
                    is_pr = "pull_request" in it
                    issues.append({
                        "number": it.get("number"),
                        "title": it.get("title"),
                        "author": it.get("user", {}).get("login"),
                        "state": it.get("state"),
                        "is_pr": is_pr,
                        "url": it.get("html_url"),
                    })

                titles = "; ".join([f"#{i['number']}: {i['title']}" for i in issues[:3]])
                speech = f"Found {len(issues)} {state} issues/PRs in {target_repo}: {titles}, sir."

                return SpecialistResult(
                    success=True,
                    action="list_issues",
                    data={"issues": issues, "repo": target_repo},
                    speech_summary=speech,
                    card_payload={"type": "github_issues_card", "repo": target_repo, "issues": issues},
                )
        except Exception as e:
            logger.exception(f"[GitHubSpecialist] List issues error: {e}")
            return SpecialistResult(success=False, action="list_issues", error=str(e))

    async def get_recent_commits(
        self,
        repo: Optional[str] = None,
        limit: int = 5,
    ) -> SpecialistResult:
        """Fetches recent commits on default branch."""
        target_repo = self._normalize_repo(repo)
        url = f"https://api.github.com/repos/{target_repo}/commits"
        params = {"per_page": limit}

        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.get(url, headers=self._get_headers(), params=params)
                if res.status_code != 200:
                    return SpecialistResult(success=False, action="get_recent_commits", error=f"GitHub API error (HTTP {res.status_code})")

                commits_data = res.json()
                commits = []
                for c in commits_data[:limit]:
                    commits.append({
                        "sha": c.get("sha", "")[:7],
                        "message": c.get("commit", {}).get("message", "").splitlines()[0],
                        "author": c.get("commit", {}).get("author", {}).get("name"),
                        "date": c.get("commit", {}).get("author", {}).get("date"),
                        "url": c.get("html_url"),
                    })

                recent_summary = ", ".join([f"'{c['message']}'" for c in commits[:2]])
                speech = f"Recent commits in {target_repo} include {recent_summary}, sir."

                return SpecialistResult(
                    success=True,
                    action="get_recent_commits",
                    data={"commits": commits, "repo": target_repo},
                    speech_summary=speech,
                    card_payload={"type": "github_commits_card", "repo": target_repo, "commits": commits},
                )
        except Exception as e:
            logger.exception(f"[GitHubSpecialist] Get recent commits error: {e}")
            return SpecialistResult(success=False, action="get_recent_commits", error=str(e))

    async def list_user_repos(
        self,
        limit: int = 5,
        sort: str = "pushed",
    ) -> SpecialistResult:
        """Lists the authenticated user's repositories, sorted by most recently active."""
        url = "https://api.github.com/user/repos"
        params = {"sort": sort, "direction": "desc", "per_page": limit, "type": "owner"}

        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.get(url, headers=self._get_headers(), params=params)
                if res.status_code == 401:
                    return SpecialistResult(
                        success=False, action="list_user_repos",
                        error="GitHub token is missing or invalid. Cannot list your repositories.",
                        speech_summary="I'm unable to access your GitHub account, sir. The authentication token may be invalid or expired.",
                    )
                if res.status_code != 200:
                    return SpecialistResult(success=False, action="list_user_repos", error=f"GitHub API error (HTTP {res.status_code}): {res.text}")

                repos_data = res.json()
                if not repos_data:
                    return SpecialistResult(
                        success=True, action="list_user_repos",
                        data={"repos": []},
                        speech_summary="You don't appear to have any repositories on GitHub, sir.",
                    )

                repos = []
                for r in repos_data[:limit]:
                    repos.append({
                        "name": r.get("full_name"),
                        "description": r.get("description") or "No description",
                        "language": r.get("language") or "Mixed",
                        "stars": r.get("stargazers_count", 0),
                        "private": r.get("private", False),
                        "pushed_at": r.get("pushed_at"),
                        "url": r.get("html_url"),
                    })

                most_recent = repos[0]
                repo_list = ", ".join([f"'{r['name'].split('/')[-1]}' ({r['language']})" for r in repos[:3]])
                speech = (
                    f"Your most recently active project is '{most_recent['name'].split('/')[-1]}' "
                    f"written in {most_recent['language']}, sir. "
                    f"Your recent repositories include {repo_list}."
                )

                return SpecialistResult(
                    success=True,
                    action="list_user_repos",
                    data={"repos": repos, "most_recent": most_recent["name"]},
                    speech_summary=speech,
                    card_payload={"type": "github_repos_card", "repos": repos},
                )
        except Exception as e:
            logger.exception(f"[GitHubSpecialist] List user repos error: {e}")
            return SpecialistResult(success=False, action="list_user_repos", error=str(e))

    # ── Action Router ────────────────────────────────────────────────────────

    async def execute(
        self, action: str, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None
    ) -> SpecialistResult:
        act = action.lower().strip()

        # 1. Repo info
        if act in ["get_repo_info", "repo_info", "repo_stats", "get_repo"]:
            return await self.get_repo_info(repo=params.get("repo"))

        # 2. Search code
        elif act in ["search_code", "code_search", "find_code"]:
            query = str(params.get("query") or params.get("search") or params.get("symbol") or "")
            return await self.search_code(query=query, repo=params.get("repo"))

        # 3. Get snippet / file content
        elif act in ["get_code_snippet", "get_snippet", "read_file", "file_content", "get_code"]:
            path = str(params.get("path") or params.get("file") or "")
            start_line = params.get("start_line") or params.get("start")
            end_line = params.get("end_line") or params.get("end")
            return await self.get_code_snippet(
                path=path,
                repo=params.get("repo"),
                start_line=int(start_line) if start_line else None,
                end_line=int(end_line) if end_line else None,
                ref=params.get("ref"),
            )

        # 4. Solve doubt / explain code
        elif act in ["solve_doubt", "explain_code", "debug_code", "doubt", "help_code"]:
            query = str(params.get("query") or params.get("question") or params.get("doubt") or "")
            return await self.solve_doubt(
                query=query,
                path=params.get("path"),
                code=params.get("code"),
                repo=params.get("repo"),
            )

        # 5. Issues / Pull Requests
        elif act in ["list_issues", "issues", "get_issues", "prs"]:
            state = str(params.get("state") or "open")
            limit = int(params.get("limit") or 5)
            return await self.list_issues(repo=params.get("repo"), state=state, limit=limit)

        # 6. Commits
        elif act in ["get_recent_commits", "recent_commits", "commits", "git_log"]:
            limit = int(params.get("limit") or 5)
            return await self.get_recent_commits(repo=params.get("repo"), limit=limit)

        # 7. List user repos
        elif act in ["list_user_repos", "list_repos", "my_repos", "recent_repos", "user_repos"]:
            limit = int(params.get("limit") or 5)
            sort = str(params.get("sort") or "pushed")
            return await self.list_user_repos(limit=limit, sort=sort)

        return SpecialistResult(success=False, action=action, error=f"Unknown action '{action}' on GitHub specialist.")
