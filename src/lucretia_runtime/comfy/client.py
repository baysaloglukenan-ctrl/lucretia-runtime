from __future__ import annotations

import json
import mimetypes
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any


class ComfyClientError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, payload: Any = None) -> None:
        self.status_code = status_code
        self.payload = payload
        suffix = f" (HTTP {status_code})" if status_code else ""
        super().__init__(message + suffix)


class ComfyClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.client_id = str(uuid.uuid4())

    @staticmethod
    def _decode_payload(raw: bytes) -> Any:
        text = raw.decode("utf-8", errors="replace")
        try:
            return json.loads(text)
        except Exception:
            return {"raw": text}

    def _open_json(self, request: str | urllib.request.Request, *, timeout: int) -> dict:
        try:
            with urllib.request.urlopen(request, timeout=timeout) as resp:
                payload = self._decode_payload(resp.read())
                return payload if isinstance(payload, dict) else {"payload": payload}
        except urllib.error.HTTPError as exc:
            payload = self._decode_payload(exc.read())
            raise ComfyClientError(
                f"ComfyUI request rejected: {payload}",
                status_code=exc.code,
                payload=payload,
            ) from exc
        except urllib.error.URLError as exc:
            raise ComfyClientError(f"ComfyUI connection failed: {exc.reason}") from exc

    def _json_get(self, path: str, timeout: int = 30) -> dict:
        return self._open_json(f"{self.base_url}{path}", timeout=timeout)

    def system_stats(self) -> dict:
        return self._json_get("/system_stats", timeout=10)

    def queue(self) -> dict:
        return self._json_get("/queue", timeout=10)

    def history(self, prompt_id: str) -> dict:
        return self._json_get(f"/history/{urllib.parse.quote(prompt_id)}", timeout=30)

    def submit_prompt(self, workflow: dict) -> dict:
        body = json.dumps({"prompt": workflow, "client_id": self.client_id}).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/prompt",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        return self._open_json(req, timeout=60)

    def upload_image(self, image_path: Path, subfolder: str = "lucretia") -> dict:
        boundary = f"----lucretia-{uuid.uuid4().hex}"
        filename = image_path.name
        content_type = mimetypes.guess_type(str(image_path))[0] or "application/octet-stream"
        chunks = []

        def add_field(name: str, value: str) -> None:
            chunks.append(f"--{boundary}\r\n".encode())
            chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
            chunks.append(value.encode())
            chunks.append(b"\r\n")

        add_field("type", "input")
        add_field("subfolder", subfolder)
        add_field("overwrite", "true")
        chunks.append(f"--{boundary}\r\n".encode())
        chunks.append(f'Content-Disposition: form-data; name="image"; filename="{filename}"\r\n'.encode())
        chunks.append(f"Content-Type: {content_type}\r\n\r\n".encode())
        chunks.append(image_path.read_bytes())
        chunks.append(b"\r\n")
        chunks.append(f"--{boundary}--\r\n".encode())
        body = b"".join(chunks)
        req = urllib.request.Request(
            f"{self.base_url}/upload/image",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}", "Content-Length": str(len(body))},
            method="POST",
        )
        return self._open_json(req, timeout=120)

    def download_view(self, filename: str, output_path: Path, subfolder: str = "", file_type: str = "output") -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        params = urllib.parse.urlencode({"filename": filename, "subfolder": subfolder, "type": file_type})
        try:
            with urllib.request.urlopen(f"{self.base_url}/view?{params}", timeout=180) as resp:
                output_path.write_bytes(resp.read())
        except urllib.error.HTTPError as exc:
            payload = self._decode_payload(exc.read())
            raise ComfyClientError(
                f"ComfyUI output download rejected: {payload}",
                status_code=exc.code,
                payload=payload,
            ) from exc
        except urllib.error.URLError as exc:
            raise ComfyClientError(f"ComfyUI output download failed: {exc.reason}") from exc
        return output_path
