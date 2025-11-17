"""
对话管理器
"""
from typing import Optional, AsyncIterator
from app.services.retriever import HybridRetriever
from app.services.llm_adapter import LLMAdapter
from app.models.schemas import ChatResponse, SourceInfo, StreamChatChunk
from app.utils.redis_client import get_redis_client
import uuid
import json
import time

# 对话历史存储配置
# 使用 Redis 存储对话历史，支持多进程共享和自动过期
MAX_HISTORY_SIZE = 1000  # 最多保留 1000 个对话
HISTORY_EXPIRE_SECONDS = 3600 * 24  # 24 小时过期
REDIS_KEY_PREFIX = "conversation:"  # Redis 键前缀


class ConversationManager:
    """对话管理器"""
    
    def __init__(self):
        # 延迟初始化，避免启动时创建重资源
        # 这些对象会在首次使用时才真正初始化内部资源
        try:
            self.retriever = HybridRetriever()
            self.llm = LLMAdapter()
            # 初始化 Redis 客户端，用于存储对话历史
            # 设置默认 TTL 为 24 小时，每次访问时自动刷新
            self.redis_client = get_redis_client(default_ttl=HISTORY_EXPIRE_SECONDS)
        except Exception as e:
            import traceback
            print(f"⚠️ ConversationManager 初始化失败: {e}")
            traceback.print_exc()
            raise
    
    async def chat(
        self,
        item_id: int,
        user_id: Optional[int],
        question: str,
        conversation_id: Optional[str] = None,
        stream: bool = False
    ) -> ChatResponse:
        """对话接口（非流式）"""
        # 获取或创建对话ID
        if not conversation_id:
            conversation_id = str(uuid.uuid4())
        
        # 加载对话历史
        history = self._load_history(conversation_id)
        
        # 检索相关文档
        relevant_docs = await self.retriever.retrieve(
            query=question,
            item_id=item_id,
            top_k=5
        )
        
        # 构建 Prompt
        prompt = self._build_prompt(question, relevant_docs, history)
        
        # 调用 LLM
        messages = [
            {"role": "system", "content": self._get_system_message()},
            {"role": "user", "content": prompt}
        ]
        
        response = await self.llm.chat(messages, stream=False)
        
        # 解析响应
        if hasattr(response, 'choices') and response.choices:
            # OpenAI 格式
            answer = response.choices[0].message.content
            usage = {
                "prompt_tokens": response.usage.prompt_tokens if hasattr(response, 'usage') and response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if hasattr(response, 'usage') and response.usage else 0,
                "total_tokens": response.usage.total_tokens if hasattr(response, 'usage') and response.usage else 0
            }
        elif hasattr(response, 'output') and response.output:
            # 通义千问格式
            answer = response.output.choices[0].message.content if response.output.choices else ""
            usage = {
                "prompt_tokens": response.usage.input_tokens if hasattr(response, 'usage') and response.usage else 0,
                "completion_tokens": response.usage.output_tokens if hasattr(response, 'usage') and response.usage else 0,
                "total_tokens": 0
            }
        else:
            # 未知格式，尝试通用解析
            answer = str(response) if response else ""
            usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        
        # 确保 answer 是 UTF-8 编码的字符串
        if answer:
            if isinstance(answer, bytes):
                answer = answer.decode('utf-8', errors='ignore')
            elif not isinstance(answer, str):
                answer = str(answer)
            # 确保是有效的 UTF-8 字符串
            answer = answer.encode('utf-8', errors='ignore').decode('utf-8')
        
        # 构建来源信息
        sources = [
            SourceInfo(
                page_id=doc["page_id"],
                page_title=doc["page_title"],
                relevance=doc["relevance"],
                snippet=doc["content"][:200],
                url=f"/{item_id}/{doc['page_id']}"
            )
            for doc in relevant_docs
        ]
        
        # 保存对话历史
        self._save_history(conversation_id, question, answer)
        
        return ChatResponse(
            conversation_id=conversation_id,
            answer=answer,
            sources=sources,
            usage=usage
        )
    
    async def chat_stream(
        self,
        item_id: int,
        user_id: Optional[int],
        question: str,
        conversation_id: Optional[str] = None
    ) -> AsyncIterator[StreamChatChunk]:
        """对话接口（流式）"""
        # 获取或创建对话ID
        if not conversation_id:
            conversation_id = str(uuid.uuid4())
        
        # 加载对话历史
        history = self._load_history(conversation_id)
        
        # 检索相关文档
        relevant_docs = await self.retriever.retrieve(
            query=question,
            item_id=item_id,
            top_k=5
        )
        
        # 构建 Prompt
        prompt = self._build_prompt(question, relevant_docs, history)
        
        # 调用 LLM（流式）
        messages = [
            {"role": "system", "content": self._get_system_message()},
            {"role": "user", "content": prompt}
        ]
        
        response = await self.llm.chat(messages, stream=True)
        
        # 流式返回
        full_answer = ""
        async for chunk in self._process_stream(response):
            full_answer += chunk
            yield StreamChatChunk(type="token", content=chunk)
        
        # 返回来源信息
        sources = [
            SourceInfo(
                page_id=doc["page_id"],
                page_title=doc["page_title"],
                relevance=doc["relevance"],
                snippet=doc["content"][:200],
                url=f"/{item_id}/{doc['page_id']}"
            )
            for doc in relevant_docs
        ]
        
        yield StreamChatChunk(type="sources", sources=sources)
        
        # 保存对话历史
        self._save_history(conversation_id, question, full_answer)
    
    async def _process_stream(self, response) -> AsyncIterator[str]:
        """处理流式响应"""
        first_chunk = True  # 标记第一个 chunk，用于日志
        if hasattr(response, '__iter__'):
            # OpenAI 格式
            for chunk in response:
                if chunk.choices and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta
                    if hasattr(delta, 'content') and delta.content:
                        content = delta.content
                        
                        # 确保内容是 UTF-8 编码的字符串
                        if isinstance(content, bytes):
                            content = content.decode('utf-8', errors='ignore')
                        elif not isinstance(content, str):
                            content = str(content)
                        # 确保是有效的 UTF-8 字符串
                        content = content.encode('utf-8', errors='ignore').decode('utf-8')
                        
                        # 第一个 chunk 标记
                        if first_chunk:
                            first_chunk = False
                        
                        yield content
        else:
            # 通义千问格式
            for chunk in response:
                if chunk.status_code == 200:
                    if chunk.output and chunk.output.choices:
                        content = chunk.output.choices[0].message.content
                        if content:
                            # 确保内容是 UTF-8 编码的字符串
                            if isinstance(content, bytes):
                                content = content.decode('utf-8', errors='ignore')
                            elif not isinstance(content, str):
                                content = str(content)
                            # 确保是有效的 UTF-8 字符串
                            content = content.encode('utf-8', errors='ignore').decode('utf-8')
                            
                            # 第一个 chunk 标记
                            if first_chunk:
                                first_chunk = False
                            
                            yield content
    
    def _get_system_message(self) -> str:
        """获取系统消息，定义 AI 助手的角色和能力"""
        return """你是一个智能的文档助手，擅长理解文档内容并回答用户问题。

核心能力：
1. **语义理解**：能够理解问题的真实意图，即使问题中的词汇与文档不完全一致，也能通过同义词、近义词、相关概念找到相关内容
2. **推理分析**：能够基于文档内容进行合理推理，但必须明确区分"文档中的信息"和"基于文档的推理结论"
3. **上下文关联**：能够理解问题的上下文，结合对话历史给出连贯的回答
4. **多角度思考**：能够从不同角度理解问题，找到最相关的文档内容

严格约束（防止幻觉）：
- **必须严格基于提供的文档内容**：所有回答必须来源于提供的文档，不能使用文档外的知识
- **禁止编造信息**：绝对不能编造、猜测或添加文档中不存在的信息
- **明确标注来源**：每个信息点都必须标注来源文档，区分"文档原文"和"推理结论"
- **不确定必须说明**：如果文档中没有相关信息或信息不完整，必须明确说明，不能猜测
- **推理需标注**：如果进行推理，必须明确说明是基于哪些文档内容的推理，并标注为"基于文档的推理"

回答原则：
- 优先直接引用文档中的准确内容（标注为"文档原文"）
- 如果找不到直接答案，可以基于文档内容进行合理推理，但必须明确标注为"基于文档的推理"
- 如果涉及多个相关文档，要全面整合信息，并分别标注来源
- 回答要清晰、有条理、易于理解
- 必须标注引用来源，方便用户查看原文
- **标注来源时，必须使用文档的完整标题（例如："用户管理"），而不是序号（例如："文档 2"）**"""
    
    def _build_prompt(
        self,
        question: str,
        relevant_docs: list,
        history: list
    ) -> str:
        """构建 Prompt"""
        # 检测是否包含 API 文档
        has_api_docs = self._detect_api_documents(relevant_docs)
        
        # 优化文档组织：去重、合并、结构化
        organized_docs = self._organize_documents(relevant_docs, has_api_docs)
        
        # 构建文档上下文（结构化组织）
        context = self._build_context(organized_docs, has_api_docs)
        
        # 构建对话历史上下文（如果有）
        history_context = ""
        if history and len(history) > 0:
            history_parts = []
            # 只取最近几轮对话，避免上下文过长
            recent_history = history[-6:] if len(history) > 6 else history
            for msg in recent_history:
                role = "用户" if msg.get("role") == "user" else "助手"
                content = msg.get("content", "")
                history_parts.append(f"{role}：{content}")
            history_context = "\n\n【对话历史】\n" + "\n".join(history_parts) + "\n"
        
        # 根据是否包含 API 文档，添加针对性的指导
        api_guidance = ""
        if has_api_docs:
            api_guidance = """
**特别说明（检测到 API 文档）**：
以下文档包含 API 接口文档。回答 API 相关问题时，请注意：
- 准确提取接口地址（HTTP 方法 + URL 路径）
- 完整列出请求参数（Headers、Query、Body），包括参数类型、是否必填、说明
- 详细说明响应格式，包括响应字段的含义和类型
- 如果文档中包含代码示例，要保持代码格式完整
- 如果用户询问"如何调用"，要提供完整的调用示例（包括请求头、请求体等）
- 如果用户询问"参数说明"，要列出所有参数及其详细说明
- 如果用户询问"返回什么"，要说明响应结构和字段含义
"""
        
        prompt = f"""请基于以下文档内容回答用户问题。注意：要理解问题的真实意图，即使问题中的词汇与文档不完全一致，也要通过语义理解、同义词匹配、相关概念关联等方式找到相关内容。

⚠️ **重要约束**：所有回答必须严格基于提供的文档内容，禁止使用文档外的知识，禁止编造任何信息。

{api_guidance}

{context}

{history_context}
【回答要求】

1. **语义理解与匹配**：
   - 理解问题的真实意图，不要局限于字面意思
   - 识别同义词、近义词、相关概念（例如："接口"和"API"、"登录"和"登入"、"用户"和"账号"等）
   - 如果问题中的词汇与文档不完全一致，要通过语义理解找到相关内容
   - **但必须确保找到的内容确实在文档中**，不能因为语义相似就编造信息

2. **信息提取与引用**：
   - 如果文档中有直接答案，优先直接引用原文（标注为"📄 文档原文"）
   - 引用时要尽量保持原文的准确性，不要修改或曲解原意
   - 可以结合多个文档片段的信息，但要分别标注每个片段的来源
   - 如果文档中只有部分相关信息，要明确说明"文档中只有部分相关信息"，并只基于现有信息回答

3. **推理与分析（需谨慎）**：
   - 如果找不到直接答案，可以基于文档中的相关内容进行合理推理
   - **但必须明确标注为"基于文档的推理"**，并说明推理依据
   - 推理必须基于文档中的明确信息，不能凭空猜测
   - 如果推理依据不足，要明确说明"文档中信息不足，无法确定"
   - 示例格式："基于文档中提到的 [具体内容]，可以推断 [推理结论]（📄 基于文档的推理，来源：[文档标题]）"

4. **回答质量**：
   - 回答要准确、清晰、有条理
   - 如果涉及步骤、列表、分类等，要结构化展示
   - 如果涉及代码、配置等，要保持格式完整
   - 如果涉及多个相关文档，要全面整合信息，并分别标注来源

5. **引用来源标注**：
   - **每个信息点都必须标注来源**，区分以下类型：
     - 📄 **文档原文**：[文档标题] - 直接来自文档的内容
     - 🔍 **基于文档的推理**：[文档标题] - 基于文档内容的推理结论
   - **重要**：标注来源时，必须使用文档的**完整标题**（例如："用户管理"、"API接口说明"），而不是序号（例如："文档 2"、"文档 3"）
   - 文档在上下文中的格式为"【文档 X：标题】"，标注来源时只需使用"标题"部分（冒号后面的内容）
   - 如果信息来自多个文档，要分别标注每个文档的完整标题
   - 格式示例：
     ```
     [回答内容]
     📄 文档原文：来源【用户管理】、【API接口说明】
     ```
   - **错误示例**（不要这样写）：
     ```
     📄 文档原文：来源【文档 2】、【文档 3】  ❌ 错误：使用了序号而不是标题
     📄 文档原文：来源【文档 2：用户管理】  ❌ 错误：包含了序号，应该只使用标题部分
     ```

6. **不确定情况处理（防止幻觉）**：
   - **如果文档中确实没有相关信息**，必须明确说明："文档中未找到相关信息"
   - **绝对不能编造或猜测答案**，即使问题很合理也不能编造
   - **如果信息不完整**，要明确说明"文档中只有部分信息"，并只回答确定的部分
   - 可以建议用户查看相关文档或提供更具体的问题
   - 如果推理依据不足，要明确说明"文档中信息不足，无法确定"

【用户问题】
{question}

请基于以上要求，严格基于文档内容，给出准确、有用的回答。记住：宁可说"不知道"，也不能编造信息。"""
        
        return prompt
    
    def _detect_api_documents(self, relevant_docs: list) -> bool:
        """
        检测文档列表中是否包含 API 文档
        
        检测策略：
        1. 检查文档的 page_type 是否为 "api"
        2. 通过文档内容特征检测（与 chunker 的检测逻辑一致）
        """
        for doc in relevant_docs:
            # 检查 metadata 中的 page_type
            metadata = doc.get("metadata", {})
            if metadata.get("page_type") == "api":
                return True
            
            # 通过内容特征检测
            content = doc.get("content", "")
            if self._is_api_content(content):
                return True
        
        return False
    
    def _is_api_content(self, content: str) -> bool:
        """
        通过内容特征检测是否为 API 文档内容
        
        检测策略与 chunker._detect_api_document 一致
        """
        if not content or not isinstance(content, str):
            return False
        
        content_lower = content.lower()
        
        # 检测 API 文档的关键特征
        api_keywords = [
            "接口地址", "**接口地址", "请求参数", "响应示例", "响应字段",
            "api", "endpoint", "method", "headers", "query", "body"
        ]
        
        # 检测 HTTP 方法
        http_methods = ["get", "post", "put", "delete", "patch", "head", "options"]
        
        # 检测 API 路径特征
        import re
        api_path_patterns = [
            r'/api/',
            r'/v\d+/',
            r'https?://[^\s]+/api/',
            r'https?://[^\s]+/v\d+/'
        ]
        
        # 检查关键词
        keyword_count = sum(1 for keyword in api_keywords if keyword in content_lower)
        
        # 检查 HTTP 方法
        method_count = sum(1 for method in http_methods if f" {method} " in content_lower or content_lower.startswith(method))
        
        # 检查 API 路径
        path_match = any(re.search(pattern, content_lower) for pattern in api_path_patterns)
        
        # 综合判断
        if "接口地址" in content and method_count > 0:
            return True
        
        if keyword_count >= 2 and method_count > 0:
            return True
        
        if path_match and method_count > 0:
            return True
        
        if ("请求参数" in content or "request" in content_lower) and \
           ("响应" in content or "response" in content_lower):
            return True
        
        return False
    
    def _organize_documents(self, relevant_docs: list, has_api_docs: bool) -> list:
        """
        优化文档组织：去重、合并、结构化
        
        策略：
        1. 按 page_id 分组，合并同一文档的多个 chunk
        2. 按相关性排序
        3. 提取关键信息（特别是 API 文档）
        4. 限制上下文长度
        """
        if not relevant_docs:
            return []
        
        # 按 page_id 分组
        docs_by_page = {}
        for doc in relevant_docs:
            page_id = doc.get("page_id")
            if page_id not in docs_by_page:
                docs_by_page[page_id] = {
                    "page_id": page_id,
                    "page_title": doc.get("page_title", ""),
                    "chunks": [],
                    "max_relevance": 0.0,
                    "metadata": doc.get("metadata", {})
                }
            
            # 添加 chunk
            chunk_info = {
                "content": doc.get("content", ""),
                "relevance": doc.get("relevance", 0.0),
                "chunk_metadata": doc.get("metadata", {}).get("chunk_metadata", {})
            }
            docs_by_page[page_id]["chunks"].append(chunk_info)
            docs_by_page[page_id]["max_relevance"] = max(
                docs_by_page[page_id]["max_relevance"],
                doc.get("relevance", 0.0)
            )
        
        # 转换为列表并按相关性排序
        organized = list(docs_by_page.values())
        organized.sort(key=lambda x: x["max_relevance"], reverse=True)
        
        # 限制文档数量（避免上下文过长）
        max_docs = 5
        organized = organized[:max_docs]
        
        # 为每个文档提取关键信息
        for doc_info in organized:
            doc_info["key_info"] = self._extract_key_info(
                doc_info["chunks"],
                doc_info["metadata"].get("page_type") == "api" or has_api_docs
            )
        
        return organized
    
    def _extract_key_info(self, chunks: list, is_api: bool = False) -> dict:
        """
        提取文档的关键信息
        
        对于 API 文档，提取：
        - 接口地址（HTTP 方法 + URL）
        - 主要参数
        - 响应格式
        
        对于普通文档，提取：
        - 标题/章节
        - 关键概念
        """
        if not chunks:
            return {}
        
        # 合并所有 chunk 的内容
        full_content = "\n\n".join([chunk.get("content", "") for chunk in chunks])
        
        if is_api:
            # 提取 API 文档的关键信息
            import re
            
            key_info = {
                "type": "api",
                "endpoints": [],
                "methods": set(),
                "has_params": False,
                "has_response": False
            }
            
            # 提取接口地址和方法
            # 匹配：**接口地址：** POST /api/xxx 或 POST /api/xxx
            endpoint_patterns = [
                r'\*\*接口地址[：:]\*\*\s*([A-Z]+)\s+([^\s\n]+)',
                r'([A-Z]+)\s+([/][^\s\n]+)',
                r'接口地址[：:]\s*([A-Z]+)\s+([^\s\n]+)'
            ]
            
            for pattern in endpoint_patterns:
                matches = re.finditer(pattern, full_content, re.IGNORECASE)
                for match in matches:
                    method = match.group(1).upper()
                    path = match.group(2)
                    key_info["endpoints"].append({"method": method, "path": path})
                    key_info["methods"].add(method)
            
            # 检测是否有参数和响应信息
            if "请求参数" in full_content or "request" in full_content.lower():
                key_info["has_params"] = True
            if "响应" in full_content or "response" in full_content.lower():
                key_info["has_response"] = True
            
            key_info["methods"] = list(key_info["methods"])
            return key_info
        else:
            # 普通文档：提取标题和关键概念
            import re
            
            # 提取标题
            headers = re.findall(r'^#{1,6}\s+(.+)$', full_content, re.MULTILINE)
            
            return {
                "type": "regular",
                "headers": headers[:5],  # 最多5个标题
                "has_code": "```" in full_content,
                "has_table": "|" in full_content and "\n|" in full_content
            }
    
    def _build_context(self, organized_docs: list, has_api_docs: bool) -> str:
        """
        构建结构化的文档上下文
        """
        if not organized_docs:
            return "（未找到相关文档）"
        
        context_parts = []
        
        for i, doc_info in enumerate(organized_docs, 1):
            page_title = doc_info.get("page_title", "未知文档")
            chunks = doc_info.get("chunks", [])
            relevance = doc_info.get("max_relevance", 0.0)
            key_info = doc_info.get("key_info", {})
            
            # 构建文档头部信息
            doc_header = f"【文档 {i}：{page_title}】"
            if relevance > 0:
                doc_header += f"（相关度：{relevance:.2f}）"
            
            # 如果是 API 文档，添加关键信息摘要
            if key_info.get("type") == "api":
                endpoints = key_info.get("endpoints", [])
                if endpoints:
                    endpoint_str = "、".join([f"{e['method']} {e['path']}" for e in endpoints[:3]])
                    doc_header += f"\n📍 接口：{endpoint_str}"
            
            context_parts.append(doc_header)
            
            # 合并同一文档的多个 chunk（去重并保持顺序）
            merged_content = self._merge_chunks(chunks)
            
            # 如果内容太长，截取最相关的部分
            max_chunk_length = 2000  # 每个文档最多 2000 字符
            if len(merged_content) > max_chunk_length:
                # 优先保留开头部分（通常包含关键信息）
                merged_content = merged_content[:max_chunk_length] + "\n\n...（内容已截断）"
            
            context_parts.append(merged_content)
            context_parts.append("")  # 空行分隔
        
        return "\n".join(context_parts)
    
    def _merge_chunks(self, chunks: list) -> str:
        """
        合并同一文档的多个 chunk，去重并保持顺序
        """
        if not chunks:
            return ""
        
        # 按相关性排序
        sorted_chunks = sorted(chunks, key=lambda x: x.get("relevance", 0.0), reverse=True)
        
        # 合并内容，去重（简单去重：如果内容完全重复则跳过）
        merged_parts = []
        seen_content = set()
        
        for chunk in sorted_chunks:
            content = chunk.get("content", "").strip()
            if not content:
                continue
            
            # 简单去重：如果内容完全相同或高度相似，跳过
            content_hash = hash(content[:100])  # 使用前100字符的hash作为简单去重
            if content_hash in seen_content:
                continue
            
            seen_content.add(content_hash)
            merged_parts.append(content)
        
        # 用分隔符连接
        return "\n\n---\n\n".join(merged_parts)
    
    def _get_redis_key(self, conversation_id: str) -> str:
        """获取 Redis 键名"""
        return f"{REDIS_KEY_PREFIX}{conversation_id}"
    
    def _load_history(self, conversation_id: str) -> list:
        """加载对话历史（从 Redis）"""
        redis_key = self._get_redis_key(conversation_id)
        
        # 从 Redis 获取对话历史（自动刷新 TTL）
        history_data = self.redis_client.get_json(redis_key, refresh_ttl=True, ttl=HISTORY_EXPIRE_SECONDS)
        
        if history_data and isinstance(history_data, dict):
            return history_data.get("messages", [])
        return []
    
    def _save_history(self, conversation_id: str, question: str, answer: str):
        """保存对话历史（到 Redis）"""
        redis_key = self._get_redis_key(conversation_id)
        
        # 从 Redis 获取现有历史（如果存在）
        history_data = self.redis_client.get_json(redis_key, refresh_ttl=False)
        
        if not history_data or not isinstance(history_data, dict):
            history_data = {
                "messages": [],
                "created_at": time.time()
            }
        
        # 添加新的对话消息
        history_data["messages"].append({
            "role": "user",
            "content": question
        })
        history_data["messages"].append({
            "role": "assistant",
            "content": answer
        })
        history_data["last_access"] = time.time()
        
        # 限制单次对话历史长度（保留最近 10 轮对话，即 20 条消息）
        if len(history_data["messages"]) > 20:
            history_data["messages"] = history_data["messages"][-20:]
        
        # 保存到 Redis，设置 TTL 为 24 小时
        # 每次保存时都会刷新 TTL，实现滑动窗口机制
        self.redis_client.set(
            redis_key,
            history_data,
            ttl=HISTORY_EXPIRE_SECONDS,
            refresh_on_access=True
        )
        
        # 检查并限制总对话数量（防止 Redis 中积累过多对话）
        # 注意：Redis 的 TTL 会自动清理过期数据，这里只是额外的保护措施
        self._enforce_max_history_size()
    
    def _enforce_max_history_size(self):
        """
        限制总对话数量（防止 Redis 中积累过多对话）
        注意：Redis 的 TTL 会自动清理过期数据，这里只是额外的保护措施
        """
        try:
            # 获取所有对话键（使用模式匹配）
            pattern = f"{REDIS_KEY_PREFIX}*"
            all_keys = self.redis_client.keys(pattern)
            
            # 如果超过最大数量，删除最旧的对话
            if len(all_keys) > MAX_HISTORY_SIZE:
                # 获取所有键的 TTL，按 TTL 排序（TTL 越小表示越旧）
                keys_with_ttl = []
                for key in all_keys:
                    ttl = self.redis_client.ttl(key)
                    if ttl > 0:  # 只处理未过期的键
                        keys_with_ttl.append((key, ttl))
                
                # 按 TTL 排序（TTL 小的在前，表示更接近过期）
                keys_with_ttl.sort(key=lambda x: x[1])
                
                # 删除最旧的对话（超过限制的部分）
                excess_count = len(all_keys) - MAX_HISTORY_SIZE
                deleted_count = 0
                for key, _ in keys_with_ttl[:excess_count]:
                    if self.redis_client.delete(key):
                        deleted_count += 1
                
                if deleted_count > 0:
                    print(f"[Conversation] 已清理 {deleted_count} 个最旧对话历史（超过限制 {MAX_HISTORY_SIZE}）")
        except Exception as e:
            # 静默处理错误，避免影响正常流程
            # Redis 的 TTL 机制会自动清理过期数据
            pass

