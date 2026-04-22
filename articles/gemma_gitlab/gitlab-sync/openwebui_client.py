"""Open WebUI API クライアント"""
from __future__ import annotations

import logging
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)


class OpenWebUIClient:
    def __init__(self, url: str, api_key: str, timeout: int = 600):
        self.url = url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
            }
        )

    def _request(self, method: str, path: str, retries: int = 3, **kwargs):
        url = f"{self.url}{path}"
        kwargs.setdefault("timeout", self.timeout)
        for attempt in range(retries):
            try:
                r = self.session.request(method, url, **kwargs)
                if not r.ok:
                    logger.error("API %s %s -> %s: %s", method, path, r.status_code, r.text[:500])
                r.raise_for_status()
                return r
            except requests.ConnectionError:
                if attempt < retries - 1:
                    logger.warning("Connection failed %s %s, retry %d/%d", method, path, attempt + 1, retries)
                    time.sleep(10)
                else:
                    raise

    def list_knowledge(self) -> list[dict]:
        r = self._request("GET", "/api/v1/knowledge/")
        data = r.json()
        if isinstance(data, dict):
            return data.get("items") or data.get("data") or []
        return data

    def get_or_create_knowledge(self, name: str, description: str = "") -> str:
        try:
            for kb in self.list_knowledge():
                if kb.get("name") == name:
                    return kb["id"]
        except requests.HTTPError as e:
            logger.warning("list_knowledge failed, will try create: %s", e)

        r = self._request(
            "POST",
            "/api/v1/knowledge/create",
            json={
                "name": name,
                "description": description,
                "access_control": None,
            },
        )
        return r.json()["id"]

    def upload_file(self, filename: str, content: bytes) -> str:
        files = {"file": (filename, content, "text/markdown")}
        # file upload endpoint expects multipart; drop Accept/Auth-only headers are fine
        url = f"{self.url}/api/v1/files/"
        r = self.session.post(url, files=files, timeout=self.timeout)
        if not r.ok:
            logger.error("upload %s -> %s: %s", filename, r.status_code, r.text[:500])
        r.raise_for_status()
        return r.json()["id"]

    def wait_processed(self, file_id: str, timeout: int = 600) -> bool:
        start = time.time()
        while time.time() - start < timeout:
            try:
                r = self._request("GET", f"/api/v1/files/{file_id}/process/status")
                status = r.json().get("status")
                if status in ("completed", "success"):
                    return True
                if status == "failed":
                    logger.warning("Processing failed: %s", file_id)
                    return False
            except requests.HTTPError:
                pass
            time.sleep(0.5)
        logger.warning("Processing timeout (%ds): %s", timeout, file_id)
        return False

    def list_files(self) -> list[dict]:
        results = []
        page = 1
        while True:
            r = self._request("GET", "/api/v1/files/", params={"page": page})
            data = r.json()
            items = data.get("items", data) if isinstance(data, dict) else data
            if not items:
                break
            results.extend(items)
            if len(items) < 50:
                break
            page += 1
        return results

    def delete_files_by_prefix(self, kb_id: str, prefix: str) -> int:
        deleted = 0
        for f in self.list_files():
            fname = f.get("filename") or f.get("meta", {}).get("name", "")
            if fname.startswith(prefix):
                self.remove_file_from_kb(kb_id, f["id"])
                deleted += 1
        return deleted

    def add_file_to_kb(self, kb_id: str, file_id: str) -> None:
        try:
            self._request(
                "POST",
                f"/api/v1/knowledge/{kb_id}/file/add",
                json={"file_id": file_id},
            )
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 400:
                logger.warning("add_file_to_kb duplicate, skipping: %s", file_id)
            else:
                raise

    def remove_file_from_kb(self, kb_id: str, file_id: str) -> None:
        try:
            self._request(
                "POST",
                f"/api/v1/knowledge/{kb_id}/file/remove",
                json={"file_id": file_id},
            )
        except requests.HTTPError as e:
            logger.warning("remove_file_from_kb failed: %s", e)

