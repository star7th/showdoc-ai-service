# 贡献指南

感谢您对 ShowDoc AI 服务的关注！我们欢迎所有形式的贡献。

## 如何贡献

### 报告问题

如果您发现了 Bug 或有功能建议，请通过以下方式提交：

1. **检查现有 Issue**：在提交新 Issue 之前，请先搜索是否已有相关问题
2. **创建 Issue**：在 [GitHub Issues](https://github.com/star7th/showdoc-ai-service/issues) 中创建新 Issue
3. **提供详细信息**：
   - 问题描述
   - 复现步骤
   - 预期行为
   - 实际行为
   - 环境信息（Python 版本、操作系统等）
   - 错误日志（如有）

### 提交代码

#### 1. Fork 仓库

1. Fork 本仓库到您的 GitHub 账号
2. 克隆您的 Fork 到本地：
   ```bash
   git clone https://github.com/your-username/showdoc-ai-service.git
   cd showdoc-ai-service
   ```

#### 2. 创建分支

```bash
git checkout -b feature/your-feature-name
# 或
git checkout -b fix/your-bug-fix
```

#### 3. 开发环境设置

```bash
# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 安装开发依赖（如有）
pip install -r requirements-dev.txt
```

#### 4. 编写代码

- 遵循项目的代码风格
- 添加必要的注释和文档
- 确保代码通过测试（如有）
- 更新相关文档

#### 5. 提交代码

```bash
# 添加修改的文件
git add .

# 提交（使用清晰的提交信息）
git commit -m "feat: 添加新功能描述"
# 或
git commit -m "fix: 修复问题描述"
```

**提交信息规范**：
- `feat:` 新功能
- `fix:` Bug 修复
- `docs:` 文档更新
- `style:` 代码格式调整（不影响功能）
- `refactor:` 代码重构
- `test:` 测试相关
- `chore:` 构建/工具相关

#### 6. 推送并创建 Pull Request

```bash
# 推送到您的 Fork
git push origin feature/your-feature-name
```

然后在 GitHub 上创建 Pull Request，并填写：
- 清晰的标题和描述
- 说明修改的内容和原因
- 关联相关 Issue（如有）

## 代码规范

### Python 代码风格

- 遵循 [PEP 8](https://www.python.org/dev/peps/pep-0008/) 代码风格
- 使用 4 个空格缩进（不使用 Tab）
- 行长度不超过 120 字符
- 函数和类添加文档字符串（docstring）

### 代码示例

```python
def retrieve_documents(self, query: str, item_id: int, top_k: int = 5) -> List[Document]:
    """
    检索相关文档
    
    Args:
        query: 查询文本
        item_id: 项目ID
        top_k: 返回文档数量
        
    Returns:
        相关文档列表
    """
    # 实现代码
    pass
```

## 开发指南

### 项目结构

```
showdoc-ai-service/
├── app/                    # 主应用代码
│   ├── routers/           # API 路由
│   ├── services/          # 业务逻辑
│   ├── models/            # 数据模型
│   └── utils/             # 工具函数
├── worker/                # Celery 异步任务
├── config/                # 配置文件
├── docs/                  # 文档
└── tests/                 # 测试（如有）
```

### 本地开发

1. **启动基础服务**：
   ```bash
   docker-compose up -d redis qdrant
   ```

2. **配置环境变量**：
   ```bash
   export SERVICE_TOKEN=your-secret-token
   export QDRANT_URL=http://localhost:6333
   export REDIS_URL=redis://localhost:6379/0
   ```

3. **启动 API 服务**：
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

4. **启动 Celery Worker**（另开终端）：
   ```bash
   celery -A worker.celery_app worker --loglevel=info
   ```

### 测试

在提交 PR 之前，请确保：
- 代码可以正常运行
- 没有明显的错误
- 新功能有相应的文档说明

## 文档贡献

文档改进同样重要！您可以：
- 修正拼写错误
- 改进文档结构
- 添加使用示例
- 翻译文档（中英文）

文档文件位于 `docs/` 目录。

## 行为准则

- 尊重所有贡献者
- 接受建设性批评
- 专注于对项目最有利的事情
- 对其他社区成员表示同理心

## 问题反馈

如果您在贡献过程中遇到任何问题，可以：
- 在 Issue 中提问
- 联系维护者

## 许可证

通过贡献代码，您同意您的贡献将在 Apache 2.0 许可证下发布。

感谢您的贡献！🎉

