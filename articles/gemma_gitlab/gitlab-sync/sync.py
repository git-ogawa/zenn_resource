#!/usr/bin/env python3
"""GitLab -> Open WebUI Knowledge Base 同期スクリプト

各プロジェクトのコード・Issue・MR を1つのドキュメントに統合してアップロードする。
これにより embedding 処理回数を大幅に削減し、同期速度を向上させる。
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import threading
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed

import urllib3
warnings.filterwarnings("ignore", category=urllib3.exceptions.InsecureRequestWarning)
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from gitlab_client import GitLabClient
from openwebui_client import OpenWebUIClient

logger = logging.getLogger("gitlab-sync")

SCRIPT_DIR = Path(__file__).parent
STATE_DIR = SCRIPT_DIR / "state"
STATE_FILE = STATE_DIR / "sync_state.json"

KB_NAME = "gitlab"

MAX_DOC_SIZE = 200_000

EXT_MAP = {
    ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
    ".go": "Go", ".java": "Java", ".rb": "Ruby", ".rs": "Rust",
    ".yaml": "YAML", ".yml": "YAML", ".json": "JSON", ".toml": "TOML",
    ".sh": "Shell", ".tf": "Terraform", ".sql": "SQL",
    ".html": "HTML", ".css": "CSS", ".vue": "Vue",
    ".jsx": "React", ".tsx": "React/TypeScript",
    ".c": "C", ".cpp": "C++", ".h": "C/C++", ".hpp": "C++",
    ".cs": "C#", ".php": "PHP", ".pl": "Perl", ".swift": "Swift",
    ".kt": "Kotlin", ".scala": "Scala", ".lua": "Lua",
    ".r": "R", ".m": "Objective-C", ".md": "Markdown",
}

DEFAULT_SYNC_EXTENSIONS = ",".join(EXT_MAP.keys())


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"projects": {}}


def save_state(state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(
        json.dumps(state, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _detect_technologies(files: list[tuple[str, str]]) -> list[str]:
    """ファイル拡張子からプロジェクトの技術スタックを推定する"""
    techs = set()
    for fpath, content in files:
        ext = os.path.splitext(fpath)[1].lower()
        if ext in EXT_MAP:
            techs.add(EXT_MAP[ext])
        # コンテンツからk8s関連キーワードを検出
        lower_content = content.lower()
        if any(kw in lower_content for kw in ["apiversion:", "kind:", "kubectl"]):
            techs.add("Kubernetes")
        if "dockerfile" in fpath.lower() or "docker-compose" in fpath.lower():
            techs.add("Docker")
        if "ansible" in fpath.lower() or "playbook" in lower_content:
            techs.add("Ansible")
        if "terraform" in lower_content or ext == ".tf":
            techs.add("Terraform")
    return sorted(techs)


def _extract_group(path_with_namespace: str) -> str:
    """path_with_namespace からグループ部分を抽出する"""
    parts = path_with_namespace.rsplit("/", 1)
    return parts[0] if len(parts) > 1 else ""


def _project_header(project) -> str:
    """各チャンクに繰り返し埋め込むプロジェクトヘッダー（Contextual Chunk Header）"""
    group = _extract_group(project.path_with_namespace)
    return (
        f"[Group: {group} | Project: {project.path_with_namespace} | "
        f"URL: {project.web_url}]\n"
    )


def make_project_summary(
    project,
    files: list[tuple[str, str]],
    issues: list,
    mrs: list,
    readme_content: str | None = None,
) -> str:
    """プロジェクトのサマリードキュメントを生成する（一覧系クエリ用）

    Issue数・MR数 等の動的カウントは含めない（MCP 経由でリアルタイム取得するため、
    静的な値を RAG に入れると矛盾が生じる）。
    """
    techs = _detect_technologies(files)
    group = _extract_group(project.path_with_namespace)
    description = project.description or ""
    if not description and readme_content:
        # README の先頭 500 文字を説明として使用
        description = readme_content[:500].strip()

    parts = []
    parts.append(f"# プロジェクト概要: {project.path_with_namespace}\n")
    parts.append(f"グループ: {group}")
    parts.append(f"URL: {project.web_url}")
    parts.append(f"説明: {description or '(説明なし)'}")
    parts.append(f"デフォルトブランチ: {project.default_branch or 'HEAD'}")
    parts.append(f"技術スタック: {', '.join(techs) if techs else '不明'}")
    parts.append(f"ファイル数: {len(files)}")
    parts.append("")
    if files:
        parts.append("## ファイル一覧\n")
        for fpath, _ in files:
            parts.append(f"- {fpath}")
        parts.append("")
    return "\n".join(parts)


def make_project_doc(
    project,
    files: list[tuple[str, str]],
    issues: list,
    mrs: list,
    issue_notes: dict[int, list[str]] | None = None,
) -> str:
    """プロジェクトの全情報を1つの Markdown ドキュメントに統合する"""
    branch = project.default_branch or "HEAD"
    ctx = _project_header(project)
    group = _extract_group(project.path_with_namespace)
    if issue_notes is None:
        issue_notes = {}
    parts = []

    # ヘッダー
    parts.append(f"# Project: {project.path_with_namespace}\n")
    parts.append(f"Group: {group}")
    parts.append(f"URL: {project.web_url}\n")
    parts.append(f"Description: {project.description or '(no description)'}\n")
    parts.append(f"Default Branch: {branch}\n")
    parts.append("")

    # ファイル一覧サマリー
    if files:
        parts.append(f"## Files ({len(files)} files)\n")
        for fpath, _ in files:
            parts.append(f"- {fpath}")
        parts.append("")

    # コードファイル（各セクションにプロジェクトヘッダーを付与）
    for fpath, content in files:
        parts.append(f"{ctx}### {fpath}\n")
        parts.append(f"File: {project.path_with_namespace}/{fpath}")
        parts.append(f"URL: {project.web_url}/-/blob/{branch}/{fpath}\n")
        parts.append(f"```\n{content}\n```\n")

    # Issues（各セクションにプロジェクトヘッダーを付与）
    if issues:
        parts.append(f"## Issues ({len(issues)} issues)\n")
        for issue in issues:
            author = getattr(issue, "author", {}) or {}
            labels = ", ".join(issue.labels or [])
            parts.append(f"{ctx}### Issue #{issue.iid}: {issue.title}\n")
            parts.append(f"State: {issue.state}")
            parts.append(f"Author: {author.get('username', 'unknown')}")
            parts.append(f"Labels: {labels}")
            parts.append(f"URL: {issue.web_url}\n")
            parts.append(f"{issue.description or '(no description)'}\n")
            # Issue コメント（意味検索の精度向上のため）
            notes = issue_notes.get(issue.iid, [])
            if notes:
                parts.append("#### Comments\n")
                for note in notes:
                    parts.append(f"{note}\n")
                parts.append("")

    # MRs（各セクションにプロジェクトヘッダーを付与）
    if mrs:
        parts.append(f"## Merge Requests ({len(mrs)} MRs)\n")
        for mr in mrs:
            author = getattr(mr, "author", {}) or {}
            labels = ", ".join(mr.labels or [])
            parts.append(f"{ctx}### MR !{mr.iid}: {mr.title}\n")
            parts.append(f"State: {mr.state}")
            parts.append(f"Author: {author.get('username', 'unknown')}")
            parts.append(f"Source: {mr.source_branch} -> Target: {mr.target_branch}")
            parts.append(f"Labels: {labels}")
            parts.append(f"URL: {mr.web_url}\n")
            parts.append(f"{mr.description or '(no description)'}\n")

    return "\n".join(parts)


def sync_project(gl: GitLabClient, owui: OpenWebUIClient, project, kb_id: str, state, config):
    slug = project.path_with_namespace.replace("/", "__")
    pid_key = str(project.id)
    pstate = state["projects"].setdefault(pid_key, {"path": ""})
    pstate["path"] = project.path_with_namespace

    # --- データ収集 ---
    code_files: list[tuple[str, str]] = []
    repo_stats: dict = {}
    try:
        for file_path, content_bytes in gl.iter_files(
            project, config["extensions"], config["max_files"], stats=repo_stats
        ):
            try:
                content = content_bytes.decode("utf-8")
                code_files.append((file_path, content))
            except Exception as e:
                logger.warning("file encode failed %s:%s: %s", slug, file_path, e)
    except Exception as e:
        logger.error("code fetch failed %s: %s", project.path_with_namespace, e)

    readme_content = None
    try:
        readme_content = gl.get_readme(project)
    except Exception as e:
        logger.debug("readme fetch failed %s: %s", project.path_with_namespace, e)

    issues = []
    try:
        issues = gl.list_issues(project)
    except Exception as e:
        logger.error("issues fetch failed %s: %s", project.path_with_namespace, e)

    issue_notes: dict[int, list[str]] = {}
    for issue in issues:
        notes = gl.list_issue_notes(issue)
        if notes:
            issue_notes[issue.iid] = notes

    mrs = []
    try:
        mrs = gl.list_mrs(project)
    except Exception as e:
        logger.error("mrs fetch failed %s: %s", project.path_with_namespace, e)

    if not code_files and not issues and not mrs:
        logger.info("  no data, skipping")
        return

    logger.info("  [%s] files=%d, issues=%d, mrs=%d, issue_comments=%d, repo_files=%d, repo_size=%d",
                slug, len(code_files), len(issues), len(mrs), sum(len(v) for v in issue_notes.values()),
                repo_stats.get("repo_files", 0), repo_stats.get("repo_size", 0))

    # --- 古いファイルを KB から削除（ファイル名パターンで特定） ---
    deleted = owui.delete_files_by_prefix(kb_id, f"{slug}")
    if deleted:
        logger.info("  deleted %d old files", deleted)

    # --- サマリードキュメント作成 ---
    summary = make_project_summary(project, code_files, issues, mrs, readme_content)
    chunks = [(f"{slug}__summary.md", summary)]

    # --- 統合ドキュメント作成・アップロード ---
    doc = make_project_doc(project, code_files, issues, mrs, issue_notes)
    doc_bytes = doc.encode("utf-8")

    if len(doc_bytes) <= MAX_DOC_SIZE:
        chunks.append((f"{slug}.md", doc))
    else:
        chunks.extend(_split_project_doc(project, code_files, issues, mrs, slug, issue_notes))

    uploaded: list[tuple[str, str, int]] = []
    for filename, chunk_doc in chunks:
        try:
            raw = chunk_doc.encode("utf-8")
            file_id = owui.upload_file(filename, raw)
            uploaded.append((filename, file_id, len(raw)))
        except Exception as e:
            logger.error("  upload failed %s: %s", filename, e)

    for filename, file_id, size in uploaded:
        try:
            ok = owui.wait_processed(file_id)
            if not ok:
                logger.warning("  Processing incomplete: %s", filename)
            owui.add_file_to_kb(kb_id, file_id)
            logger.info("  uploaded %s (%d bytes) -> %s", filename, size, file_id)
        except Exception as e:
            logger.error("  post-process failed %s: %s", filename, e)


def _split_project_doc(
    project,
    code_files,
    issues,
    mrs,
    slug,
    issue_notes: dict[int, list[str]] | None = None,
) -> list[tuple[str, str]]:
    """大きなプロジェクトをコード/Issues/MRsの3つに分割する"""
    chunks = []
    branch = project.default_branch or "HEAD"
    ctx = _project_header(project)
    group = _extract_group(project.path_with_namespace)
    if issue_notes is None:
        issue_notes = {}
    header = (
        f"# Project: {project.path_with_namespace}\n"
        f"Group: {group}\n"
        f"URL: {project.web_url}\n"
        f"Description: {project.description or '(no description)'}\n\n"
    )

    if code_files:
        parts = [header, f"## Code Files ({len(code_files)} files)\n\n"]
        for fpath, _ in code_files:
            parts.append(f"- {fpath}\n")
        parts.append("\n")
        for fpath, content in code_files:
            parts.append(f"{ctx}### {fpath}\n\n")
            parts.append(f"URL: {project.web_url}/-/blob/{branch}/{fpath}\n\n")
            parts.append(f"```\n{content}\n```\n\n")
        chunks.append((f"{slug}__code.md", "".join(parts)))

    if issues:
        parts = [header, f"## Issues ({len(issues)} issues)\n\n"]
        for issue in issues:
            author = getattr(issue, "author", {}) or {}
            parts.append(f"{ctx}### Issue #{issue.iid}: {issue.title}\n\n")
            parts.append(f"State: {issue.state}\nAuthor: {author.get('username', 'unknown')}\n")
            parts.append(f"URL: {issue.web_url}\n\n")
            parts.append(f"{issue.description or '(no description)'}\n\n")
            notes = issue_notes.get(issue.iid, [])
            if notes:
                parts.append("#### Comments\n\n")
                for note in notes:
                    parts.append(f"{note}\n\n")
        chunks.append((f"{slug}__issues.md", "".join(parts)))

    if mrs:
        parts = [header, f"## Merge Requests ({len(mrs)} MRs)\n\n"]
        for mr in mrs:
            author = getattr(mr, "author", {}) or {}
            parts.append(f"{ctx}### MR !{mr.iid}: {mr.title}\n\n")
            parts.append(f"State: {mr.state}\nAuthor: {author.get('username', 'unknown')}\n")
            parts.append(f"URL: {mr.web_url}\n\n")
            parts.append(f"{mr.description or '(no description)'}\n\n")
        chunks.append((f"{slug}__mrs.md", "".join(parts)))

    return chunks


def make_group_summary(group, project_count: int, project_paths: list[str]) -> str:
    """グループ単位のサマリードキュメントを生成する

    「リポジトリ数が多いグループ Top3」のような集計クエリに RAG で回答するための文書。
    MCP の Tool Calling が失敗した場合のフォールバックとしても機能する。
    """
    parts = []
    parts.append(f"# グループ概要: {group.full_path}\n")
    parts.append(f"グループ名: {group.name}")
    parts.append(f"グループパス: {group.full_path}")
    parts.append(f"URL: {group.web_url}")
    parts.append(f"説明: {getattr(group, 'description', '') or '(説明なし)'}")
    parts.append(f"配下プロジェクト数: {project_count}")
    parts.append("")
    if project_paths:
        parts.append("## 配下プロジェクト一覧\n")
        for path in sorted(project_paths):
            parts.append(f"- {path}")
        parts.append("")
    return "\n".join(parts)


def sync_group_summaries(
    gl: GitLabClient, owui: OpenWebUIClient, kb_id: str,
) -> None:
    """全グループのサマリーを生成して KB にアップロードする"""
    logger.info("Syncing group summaries...")

    try:
        groups = gl.list_groups()
    except Exception:
        logger.exception("Failed to list groups")
        return

    for group in groups:
        try:
            projects = group.projects.list(
                all=True, include_subgroups=True, archived=False,
            )
            project_paths = [p.path_with_namespace for p in projects]
            project_count = len(projects)
        except Exception as e:
            logger.error("Failed to list projects for group %s: %s", group.full_path, e)
            continue

        summary = make_group_summary(group, project_count, project_paths)
        slug = group.full_path.replace("/", "__")
        filename = f"group__{slug}__summary.md"

        owui.delete_files_by_prefix(kb_id, filename)

        try:
            file_id = owui.upload_file(filename, summary.encode("utf-8"))
            ok = owui.wait_processed(file_id)
            if not ok:
                logger.warning("  Processing incomplete: %s", filename)
            owui.add_file_to_kb(kb_id, file_id)
            logger.info("  group summary: %s (%d projects) -> %s", group.full_path, project_count, file_id)
        except Exception as e:
            logger.error("  group summary upload failed %s: %s", group.full_path, e)

    logger.info("Group summaries sync complete (%d groups)", len(groups))


def load_config() -> dict:
    env_path = SCRIPT_DIR.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)

    required = ["GITLAB_URL", "GITLAB_TOKEN", "OPEN_WEBUI_API_KEY"]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        sys.exit(f"Missing env vars: {', '.join(missing)}")

    return {
        "gitlab_url": os.environ["GITLAB_URL"],
        "gitlab_token": os.environ["GITLAB_TOKEN"],
        "owui_url": os.environ.get("OPEN_WEBUI_URL", "http://localhost:3000"),
        "owui_key": os.environ["OPEN_WEBUI_API_KEY"],
        "extensions": [
            x.strip()
            for x in os.environ.get("SYNC_EXTENSIONS", DEFAULT_SYNC_EXTENSIONS).split(",")
            if x.strip()
        ],
        "max_files": int(os.environ.get("MAX_FILES_PER_REPO", "500")),
        "group_ids": [
            x.strip()
            for x in os.environ.get("GITLAB_GROUP_IDS", "").split(",")
            if x.strip()
        ],
        "visibility": os.environ.get("GITLAB_VISIBILITY") or None,
    }


def _is_changed(project, state: dict) -> bool:
    """プロジェクトの last_activity_at が前回同期時から変更されたか判定する"""
    pid_key = str(project.id)
    pstate = state.get("projects", {}).get(pid_key, {})
    prev = pstate.get("last_activity_at")
    current = getattr(project, "last_activity_at", None)
    if prev is None or current is None:
        return True
    return current != prev


def run_sync(args) -> int:
    """1回分の同期を実行する"""
    config = load_config()

    gl = GitLabClient(config["gitlab_url"], config["gitlab_token"])
    owui = OpenWebUIClient(config["owui_url"], config["owui_key"])

    if args.project:
        projects = [gl.get_project(p) for p in args.project]
    else:
        projects = gl.list_projects(
            group_ids=config["group_ids"] or None,
            visibility=config["visibility"],
        )

    projects = list(projects)
    if args.limit:
        projects = projects[: args.limit]

    logger.info("Target projects: %d", len(projects))

    if args.dry_run:
        for p in projects:
            print(f"{p.id}\t{p.path_with_namespace}")
        return 0

    kb_id = owui.get_or_create_knowledge(KB_NAME, "GitLab projects (code, issues, MRs)")
    logger.info("Knowledge Base: %s", kb_id)

    state = load_state()

    # --- グループサマリー同期 ---
    if not args.project:
        sync_group_summaries(gl, owui, kb_id)

    # --- プロジェクト同期 ---
    synced = 0
    skipped = 0
    state_lock = threading.Lock()

    targets: list[tuple[int, object]] = []
    for i, project in enumerate(projects, 1):
        if not args.force and not args.project and not _is_changed(project, state):
            skipped += 1
            logger.debug("[%d/%d] %s (unchanged, skipped)", i, len(projects), project.path_with_namespace)
            continue
        targets.append((i, project))

    max_workers = int(os.environ.get("SYNC_WORKERS", "2"))

    def _sync_one(idx: int, project) -> bool:
        logger.info("[%d/%d] %s", idx, len(projects), project.path_with_namespace)
        try:
            sync_project(gl, owui, project, kb_id, state, config)
            with state_lock:
                pid_key = str(project.id)
                pstate = state["projects"].setdefault(pid_key, {})
                pstate["last_activity_at"] = getattr(project, "last_activity_at", None)
                save_state(state)
            return True
        except Exception:
            logger.exception("project sync failed: %s", project.path_with_namespace)
            return False

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_sync_one, idx, proj): proj for idx, proj in targets}
        for future in as_completed(futures):
            if future.result():
                synced += 1

    state["last_sync"] = datetime.now(timezone.utc).isoformat()
    save_state(state)
    logger.info("Sync complete: %d synced, %d skipped (unchanged)", synced, skipped)
    return 0


SYNC_INTERVAL = int(os.environ.get("SYNC_INTERVAL", "1800"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync GitLab -> Open WebUI")
    sub = parser.add_subparsers(dest="command")

    run_parser = sub.add_parser("run", help="同期を実行する")
    run_parser.add_argument(
        "--project",
        action="append",
        help="特定プロジェクト(namespace/path または ID)。複数指定可",
    )
    run_parser.add_argument("--limit", type=int, help="同期するプロジェクト数の上限")
    run_parser.add_argument("--dry-run", action="store_true", help="対象一覧を表示のみ")
    run_parser.add_argument("--force", action="store_true", help="変更検知を無視して全件同期")
    run_parser.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    logging.basicConfig(
        level=logging.DEBUG if getattr(args, "verbose", False) else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("gitlab").setLevel(logging.WARNING)

    if args.force or args.project or args.dry_run:
        return run_sync(args)

    logger.info("Starting periodic sync (interval=%ds)", SYNC_INTERVAL)
    while True:
        try:
            run_sync(args)
        except Exception:
            logger.exception("Sync failed")
        logger.info("Next sync in %ds", SYNC_INTERVAL)
        time.sleep(SYNC_INTERVAL)


if __name__ == "__main__":
    sys.exit(main())
