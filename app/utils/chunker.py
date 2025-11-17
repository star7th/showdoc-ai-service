"""
Markdown 文档分块器
"""
from typing import List, Optional
from dataclasses import dataclass
import re


@dataclass
class Chunk:
    """文档块"""
    content: str
    metadata: dict = None


class MarkdownChunker:
    """基于 Markdown 结构的通用分块策略"""
    
    def __init__(self, max_chunk_size: int = 1000, chunk_overlap: int = 100):
        self.max_chunk_size = max_chunk_size
        self.chunk_overlap = chunk_overlap
    
    def chunk(self, markdown_content: str, page_type: str = "regular") -> List[Chunk]:
        """
        分块入口，根据文档类型选择分块策略
        
        Args:
            markdown_content: Markdown 内容
            page_type: 页面类型（regular/api/table等），但会通过内容特征进一步验证
        """
        # 检测是否为 API 文档（优先使用内容特征，page_type 作为辅助）
        is_api_doc = self._detect_api_document(markdown_content, page_type)
        
        if is_api_doc:
            return self._chunk_api_document(markdown_content)
        else:
            return self._chunk_regular_document(markdown_content)
    
    def _detect_api_document(self, markdown_content: str, page_type: str = "regular") -> bool:
        """
        检测是否为 API 文档
        
        检测策略：
        1. 如果 page_type == "api"，直接返回 True
        2. 通过内容特征检测：
           - 包含"接口地址"、"请求参数"、"响应示例"等关键词
           - 包含 HTTP 方法（GET、POST、PUT、DELETE等）
           - 包含 API 路径特征（如 /api/、/v1/ 等）
        
        Args:
            markdown_content: Markdown 内容
            page_type: 页面类型
        
        Returns:
            bool: 是否为 API 文档
        """
        # 如果明确标记为 API 文档，直接返回
        if page_type == "api":
            return True
        
        # 通过内容特征检测
        if not markdown_content or not isinstance(markdown_content, str):
            return False
        
        content_lower = markdown_content.lower()
        
        # 检测 API 文档的关键特征
        api_keywords = [
            "接口地址", "**接口地址", "请求参数", "响应示例", "响应字段",
            "api", "endpoint", "method", "headers", "query", "body"
        ]
        
        # 检测 HTTP 方法
        http_methods = ["get", "post", "put", "delete", "patch", "head", "options"]
        
        # 检测 API 路径特征
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
        import re
        path_match = any(re.search(pattern, content_lower) for pattern in api_path_patterns)
        
        # 综合判断：如果满足多个条件，认为是 API 文档
        # 条件1：包含"接口地址"且包含 HTTP 方法
        if "接口地址" in markdown_content and method_count > 0:
            return True
        
        # 条件2：包含多个 API 关键词（至少2个）且包含 HTTP 方法
        if keyword_count >= 2 and method_count > 0:
            return True
        
        # 条件3：包含 API 路径特征且包含 HTTP 方法
        if path_match and method_count > 0:
            return True
        
        # 条件4：包含"请求参数"和"响应"相关关键词
        if ("请求参数" in markdown_content or "request" in content_lower) and \
           ("响应" in markdown_content or "response" in content_lower):
            return True
        
        return False
    
    def _chunk_api_document(self, markdown_content: str) -> List[Chunk]:
        """
        针对 API 文档的优化分块策略
        
        API 文档特点：
        1. 有明确的接口结构：接口基本信息、请求参数、响应信息
        2. 用户查询时通常需要完整的接口信息
        3. 保持接口的语义完整性很重要
        """
        if not markdown_content or not isinstance(markdown_content, str):
            return [Chunk(content="", metadata={"chunk_type": "api"})]
        
        # 识别 API 文档的主要结构
        # 典型的 API 文档结构：
        # # 接口标题
        # **接口地址：** METHOD /path
        # **接口描述：** ...
        # ## 请求参数
        # ### Headers / Query / Body
        # ## 响应示例
        # ## 响应字段说明
        
        chunks = []
        lines = markdown_content.split('\n')
        
        # 识别接口边界（通常以 # 开头，且包含"接口地址"）
        current_api = []  # 当前接口的所有内容
        current_section = []  # 当前章节的内容
        in_api = False  # 是否在接口块中
        
        i = 0
        while i < len(lines):
            line = lines[i]
            
            # 检查是否是新的接口开始（一级标题，且可能是接口标题）
            is_api_header = re.match(r'^#\s+(.+)$', line)
            has_api_info = False
            
            # 检查接下来几行是否包含"接口地址"（API 文档的特征）
            if is_api_header:
                lookahead = '\n'.join(lines[i:min(i+10, len(lines))])
                if '接口地址' in lookahead or '**接口地址：**' in lookahead:
                    has_api_info = True
            
            if is_api_header and has_api_info:
                # 遇到新接口，保存上一个接口
                if current_api:
                    api_chunks = self._split_api_into_chunks('\n'.join(current_api))
                    chunks.extend(api_chunks)
                # 开始新接口
                current_api = [line]
                in_api = True
            elif in_api:
                # 检查是否是新的接口（另一个一级标题）
                if re.match(r'^#\s+(.+)$', line):
                    # 保存当前接口
                    if current_api:
                        api_chunks = self._split_api_into_chunks('\n'.join(current_api))
                        chunks.extend(api_chunks)
                    # 开始新接口
                    current_api = [line]
                else:
                    current_api.append(line)
            else:
                # 不在接口块中，按通用策略处理
                if not current_section:
                    current_section = [line]
                else:
                    current_section.append(line)
            
            i += 1
        
        # 处理最后一个接口或通用内容
        if current_api:
            api_chunks = self._split_api_into_chunks('\n'.join(current_api))
            chunks.extend(api_chunks)
        elif current_section:
            # 如果没有识别到 API 结构，回退到通用分块
            return self._chunk_regular_document(markdown_content)
        
        return chunks if chunks else [Chunk(content=markdown_content, metadata={"chunk_type": "api"})]
    
    def _split_api_into_chunks(self, api_content: str) -> List[Chunk]:
        """
        将一个 API 接口分割成多个块（如果太长）
        尽量保持语义完整性
        """
        if len(api_content) <= self.max_chunk_size:
            # 接口内容不长，保持完整
            return [Chunk(
                content=api_content,
                metadata={"chunk_type": "api", "api_complete": True}
            )]
        
        # 接口内容太长，需要分割
        # 按语义单元分割：基本信息、请求参数、响应信息
        
        chunks = []
        lines = api_content.split('\n')
        
        # 识别语义单元边界
        # 1. 接口基本信息（从开头到"请求参数"之前）
        # 2. 请求参数（## 请求参数 到 ## 响应示例 之前）
        # 3. 响应信息（## 响应示例 之后）
        
        sections = []
        current_section = []
        current_section_type = "basic"  # basic/request/response
        
        for line in lines:
            # 检测章节标题
            if re.match(r'^##\s+请求参数', line):
                if current_section:
                    sections.append(('\n'.join(current_section), current_section_type))
                current_section = [line]
                current_section_type = "request"
            elif re.match(r'^##\s+响应', line):
                if current_section:
                    sections.append(('\n'.join(current_section), current_section_type))
                current_section = [line]
                current_section_type = "response"
            else:
                current_section.append(line)
        
        # 保存最后一个章节
        if current_section:
            sections.append(('\n'.join(current_section), current_section_type))
        
        # 处理每个章节
        for section_content, section_type in sections:
            if len(section_content) <= self.max_chunk_size:
                # 章节不长，保持完整
                chunks.append(Chunk(
                    content=section_content,
                    metadata={
                        "chunk_type": "api",
                        "api_section": section_type,
                        "api_complete": False
                    }
                ))
            else:
                # 章节太长，按段落分割
                sub_chunks = self._split_large_section(section_content)
                # 为每个子块添加 API 元数据
                for chunk in sub_chunks:
                    if chunk.metadata is None:
                        chunk.metadata = {}
                    chunk.metadata.update({
                        "chunk_type": "api",
                        "api_section": section_type,
                        "api_complete": False
                    })
                chunks.extend(sub_chunks)
        
        return chunks
    
    def _chunk_regular_document(self, markdown_content: str) -> List[Chunk]:
        """
        通用文档的分块策略（原有逻辑）
        """
        # 检查输入是否为空
        if not markdown_content or not isinstance(markdown_content, str):
            return [Chunk(content="", metadata={})]
        
        # 按标题分割
        sections = self._split_by_headers(markdown_content)
        
        chunks = []
        for section in sections:
            # 如果块太大，进一步分割
            if len(section) > self.max_chunk_size:
                sub_chunks = self._split_large_section(section)
                chunks.extend(sub_chunks)
            else:
                chunks.append(Chunk(content=section, metadata={}))
        
        return chunks
    
    
    def _split_by_headers(self, content: str) -> List[str]:
        """按标题分割"""
        # 检查输入是否为空
        if not content or not isinstance(content, str):
            return [""]
        
        # 匹配所有标题（# 到 ######）
        header_pattern = r'^(#{1,6})\s+(.+)$'
        
        lines = content.split('\n')
        sections = []
        current_section = []
        current_header = None
        
        for line in lines:
            match = re.match(header_pattern, line)
            if match:
                # 遇到新标题，保存当前块
                if current_section:
                    sections.append('\n'.join(current_section))
                # 开始新块
                current_section = [line]
                current_header = line
            else:
                current_section.append(line)
        
        # 保存最后一个块
        if current_section:
            sections.append('\n'.join(current_section))
        
        # 如果没有标题，整个文档作为一个块
        if not sections:
            sections = [content]
        
        return sections
    
    def _split_large_section(self, section: str) -> List[Chunk]:
        """分割大块（在段落边界处切分）"""
        # 按段落分割（双换行）
        paragraphs = section.split('\n\n')
        
        chunks = []
        current_chunk = []
        current_size = 0
        
        for para in paragraphs:
            para_size = len(para)
            
            # 如果当前块加上新段落会超过限制，保存当前块
            if current_size + para_size > self.max_chunk_size and current_chunk:
                chunks.append(Chunk(
                    content='\n\n'.join(current_chunk),
                    metadata={}
                ))
                # 保留重叠部分
                if self.chunk_overlap > 0 and current_chunk:
                    overlap_text = '\n\n'.join(current_chunk[-1:])
                    current_chunk = [overlap_text] if len(overlap_text) < self.chunk_overlap else []
                    current_size = len(overlap_text)
                else:
                    current_chunk = []
                    current_size = 0
            
            current_chunk.append(para)
            current_size += para_size + 2  # +2 for \n\n
        
        # 保存最后一个块
        if current_chunk:
            chunks.append(Chunk(
                content='\n\n'.join(current_chunk),
                metadata={}
            ))
        
        return chunks

