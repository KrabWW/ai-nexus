"""FeishuProxy — 通过 httpx 代理调用飞书 Open API。

提供飞书知识库文档的读取功能，支持：
- 获取租户访问令牌 (tenant_access_token)
- 列出知识空间中的文档
- 读取文档内容
"""

import hashlib
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class FeishuProxy:
    """代理飞书 Open API，暴露文档读取功能。

    飞书 API 文档: https://open.feishu.cn/document/server-docs/docs
    """

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        base_url: str = "https://open.feishu.cn/open-apis",
        timeout: float = 10.0,
    ) -> None:
        """初始化飞书代理。

        Args:
            app_id: 飞书应用 ID
            app_secret: 飞书应用密钥
            base_url: 飞书 Open API 基础 URL
            timeout: 请求超时时间（秒）
        """
        self._app_id = app_id
        self._app_secret = app_secret
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._token: str | None = None

    async def get_tenant_access_token(self) -> str:
        """获取租户访问令牌。

        使用 app_id 和 app_secret 获取 tenant_access_token，
        该 token 有效期为 2 小时，会在内存中缓存。

        Returns:
            tenant_access_token 字符串

        Raises:
            httpx.HTTPError: API 请求失败时
        """
        if self._token:
            return self._token

        url = f"{self._base_url}/auth/v3/tenant_access_token/internal"
        payload = {
            "app_id": self._app_id,
            "app_secret": self._app_secret,
        }

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

            if data.get("code") != 0:
                error_msg = data.get("msg", "Unknown error")
                raise httpx.HTTPError(f"Feishu API error: {error_msg}")

            self._token = data.get("tenant_access_token")
            if not self._token:
                raise httpx.HTTPError("No tenant_access_token in response")

            return self._token

    async def list_space_docs(self, space_id: str) -> list[dict[str, Any]]:
        """列出飞书知识空间中的所有文档。

        Args:
            space_id: 飞书知识空间 ID

        Returns:
            文档列表，每个文档包含:
            - doc_token: 文档唯一标识
            - title: 文档标题
            - type: 文档类型

        Raises:
            httpx.HTTPError: API 请求失败时
        """
        token = await self.get_tenant_access_token()
        url = f"{self._base_url}/docx/v1/documents/?space_id={space_id}"

        headers = {"Authorization": f"Bearer {token}"}
        docs: list[dict[str, Any]] = []
        page_token = ""

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            while True:
                params = {"page_size": 50}
                if page_token:
                    params["page_token"] = page_token

                response = await client.get(url, headers=headers, params=params)
                response.raise_for_status()
                data = response.json()

                if data.get("code") != 0:
                    error_msg = data.get("msg", "Unknown error")
                    logger.warning("Feishu API error: %s", error_msg)
                    break

                items = data.get("data", {}).get("items", [])
                for item in items:
                    docs.append({
                        "doc_token": item.get("document", {}).get("document_id"),
                        "title": item.get("title", ""),
                        "type": item.get("document", {}).get("type", ""),
                    })

                # Check if there are more pages
                has_more = data.get("data", {}).get("has_more", False)
                if not has_more:
                    break
                page_token = data.get("data", {}).get("page_token", "")

        return docs

    async def get_doc_content(self, doc_token: str) -> str:
        """获取飞书文档的纯文本内容。

        Args:
            doc_token: 文档唯一标识

        Returns:
            文档的纯文本内容

        Raises:
            httpx.HTTPError: API 请求失败时
        """
        token = await self.get_tenant_access_token()

        # First, get the document to retrieve the latest revision ID
        doc_url = f"{self._base_url}/docx/v1/documents/{doc_token}"
        headers = {"Authorization": f"Bearer {token}"}

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(doc_url, headers=headers)
            response.raise_for_status()
            data = response.json()

            if data.get("code") != 0:
                error_msg = data.get("msg", "Unknown error")
                raise httpx.HTTPError(f"Feishu API error: {error_msg}")

            revision_id = data.get("data", {}).get("revision_id")

        # Get document blocks (content)
        blocks_url = f"{self._base_url}/docx/v1/documents/{doc_token}/blocks/{revision_id}"
        headers = {"Authorization": f"Bearer {token}"}

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(blocks_url, headers=headers)
            response.raise_for_status()
            data = response.json()

            if data.get("code") != 0:
                error_msg = data.get("msg", "Unknown error")
                logger.warning("Feishu API error: %s", error_msg)
                return ""

            # Extract text from blocks
            blocks = data.get("data", {}).get("items", [])
            text_parts: list[str] = []

            for block in blocks:
                block_type = block.get("block_type", "")
                if block_type == "text":
                    # Extract text runs
                    text_runs = block.get("text", {}).get("elements", [])
                    for run in text_runs:
                        if run.get("type") == "text_run":
                            text_parts.append(run.get("text_run", {}).get("content", ""))
                elif block_type == "heading1":
                    heading = block.get("heading1", {}).get("elements", [])
                    for run in heading:
                        if run.get("type") == "text_run":
                            text_parts.append("# " + run.get("text_run", {}).get("content", ""))
                elif block_type == "heading2":
                    heading = block.get("heading2", {}).get("elements", [])
                    for run in heading:
                        if run.get("type") == "text_run":
                            text_parts.append("## " + run.get("text_run", {}).get("content", ""))
                elif block_type == "heading3":
                    heading = block.get("heading3", {}).get("elements", [])
                    for run in heading:
                        if run.get("type") == "text_run":
                            text_parts.append("### " + run.get("text_run", {}).get("content", ""))
                elif block_type == "bullet":
                    # Bullet list items
                    for item in block.get("bullet", {}).get("elements", []):
                        if item.get("type") == "text_run":
                            text_parts.append("- " + item.get("text_run", {}).get("content", ""))
                elif block_type == "orderedList":
                    # Ordered list items
                    for item in block.get("orderedList", {}).get("elements", []):
                        if item.get("type") == "text_run":
                            text_parts.append("1. " + item.get("text_run", {}).get("content", ""))

            return "\n".join(text_parts)

    @staticmethod
    def compute_content_hash(content: str) -> str:
        """计算文档内容的 SHA256 哈希值。

        用于增量导入时判断文档是否发生变化。

        Args:
            content: 文档内容字符串

        Returns:
            十六进制格式的 SHA256 哈希值
        """
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    async def is_available(self) -> bool:
        """检查飞书服务是否可达。

        Returns:
            True 如果服务可用，False 否则
        """
        try:
            await self.get_tenant_access_token()
            return True
        except Exception:
            return False
