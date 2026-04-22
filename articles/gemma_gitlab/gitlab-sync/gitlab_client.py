"""GitLab API クライアント（python-gitlab のラッパー）"""
from __future__ import annotations

import io
import logging
import tarfile
from typing import Iterator, Optional

import gitlab

logger = logging.getLogger(__name__)

MAX_FILE_SIZE = 500_000  # 500KB 以上のファイルはスキップ


class GitLabClient:
    def __init__(self, url: str, token: str):
        self.gl = gitlab.Gitlab(url, private_token=token, timeout=60, ssl_verify=False)
        self.gl.auth()

    def list_groups(self) -> list:
        """全グループを取得する（サブグループ含む）"""
        return self.gl.groups.list(all=True)

    def list_group_project_count(self, group) -> int:
        """グループ配下のプロジェクト数を取得する（サブグループ含む）"""
        projects = group.projects.list(
            all=True, include_subgroups=True, archived=False,
        )
        return len(projects)

    def list_projects(
        self,
        group_ids: Optional[list[str]] = None,
        visibility: Optional[str] = None,
    ) -> list:
        projects: list = []
        if group_ids:
            for gid in group_ids:
                group = self.gl.groups.get(gid)
                for p in group.projects.list(all=True, include_subgroups=True, archived=False):
                    projects.append(self.gl.projects.get(p.id))
        else:
            kwargs = {"all": True, "archived": False}
            if visibility:
                kwargs["visibility"] = visibility
            projects = self.gl.projects.list(**kwargs)
        return projects

    def get_project(self, project_id_or_path):
        return self.gl.projects.get(project_id_or_path)

    def iter_files(
        self,
        project,
        extensions: list[str],
        max_files: int,
        stats: dict | None = None,
    ) -> Iterator[tuple[str, bytes]]:
        """プロジェクトのアーカイブを取得し、対象ファイルを (path, content) で返す

        stats を渡すと repo_files (全ファイル数) と repo_size (全ファイルバイト合計) を格納する。
        """
        if not project.default_branch:
            logger.info("Empty repo, skipping: %s", project.path_with_namespace)
            return

        try:
            data = project.repository_archive(format="tar.gz")
        except Exception as e:
            logger.error("Failed to fetch archive %s: %s", project.path_with_namespace, e)
            return

        count = 0
        try:
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
                members = [m for m in tar.getmembers() if m.isfile()]
                if stats is not None:
                    stats["repo_files"] = len(members)
                    stats["repo_size"] = sum(m.size for m in members)

                for member in members:
                    if member.size > MAX_FILE_SIZE:
                        continue

                    parts = member.name.split("/", 1)
                    if len(parts) < 2:
                        continue
                    path = parts[1]
                    if not path:
                        continue

                    if extensions and not any(path.endswith(ext) for ext in extensions):
                        continue

                    if max_files and count >= max_files:
                        logger.info(
                            "max_files reached (%d) for %s",
                            max_files,
                            project.path_with_namespace,
                        )
                        break

                    f = tar.extractfile(member)
                    if f is None:
                        continue
                    content = f.read()

                    try:
                        content.decode("utf-8")
                    except UnicodeDecodeError:
                        continue

                    yield path, content
                    count += 1
        except tarfile.TarError as e:
            logger.error("Tar parse error %s: %s", project.path_with_namespace, e)

    def get_readme(self, project) -> Optional[str]:
        """プロジェクトの README 内容を取得する。存在しない場合は None"""
        if not project.default_branch:
            return None
        for name in ["README.md", "readme.md", "README.rst", "README", "README.txt"]:
            try:
                f = project.files.get(file_path=name, ref=project.default_branch)
                return f.decode().decode("utf-8")
            except Exception:
                continue
        return None

    def list_issues(self, project) -> list:
        return project.issues.list(all=True, state="all")

    def list_issue_notes(self, issue, max_notes: int = 20) -> list[str]:
        """Issue のコメント（ノート）を取得する。system ノートは除外"""
        notes = []
        try:
            for note in issue.notes.list(all=True, sort="asc"):
                if getattr(note, "system", False):
                    continue
                body = getattr(note, "body", "")
                if body:
                    notes.append(body)
                if len(notes) >= max_notes:
                    break
        except Exception as e:
            logger.debug("notes fetch failed for issue %s: %s", issue.iid, e)
        return notes

    def list_mrs(self, project) -> list:
        return project.mergerequests.list(all=True, state="all")
