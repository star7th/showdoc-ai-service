# ShowDoc AI 服务

ShowDoc AI 知识库的后端服务，提供文档索引、RAG 检索和智能问答功能。

## 快速开始

### 1. 准备配置

```bash
# 复制环境变量配置
cp env.example .env
# 编辑 .env 文件，设置 SERVICE_TOKEN

# 复制 LLM 配置文件
cp config/llm.yaml.example config/llm.yaml
# 编辑 config/llm.yaml，配置你的 LLM API Key
```

### 2. 下载模型

**必须**：在构建 Docker 镜像之前，先手动下载模型文件到 `models/bge-base-zh-v1.5/` 目录。

详细步骤：参考 [模型下载指南](docs/manual-model-download.md)

### 3. 启动服务

```bash
# 构建并启动所有服务
docker-compose up -d

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f

# 验证服务
curl http://localhost:7125/api/health
```

### 4. 访问 API 文档

启动服务后访问：http://localhost:7125/docs

## 本地开发

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 启动基础服务（Redis 和 Qdrant）
docker-compose up -d redis qdrant

# 3. 配置环境变量
export SERVICE_TOKEN=your-secret-token
export QDRANT_URL=http://localhost:6333
export REDIS_URL=redis://localhost:6379/0

# 4. 配置 LLM
cp config/llm.yaml.example config/llm.yaml
# 编辑 config/llm.yaml

# 5. 启动服务
uvicorn app.main:app --host 0.0.0.0 --port 8000

# 6. 启动 Celery Worker（另开终端）
celery -A worker.celery_app worker --loglevel=info
```

## 服务端口

- **AI API 服务**: `http://localhost:7125`
- **Qdrant**: 仅内部使用
- **Redis**: 仅内部使用

## 常见问题

### 模型下载

模型必须手动下载到 `models/bge-base-zh-v1.5/` 目录，参考 [模型下载指南](docs/manual-model-download.md)

### CentOS 7 启动失败

如果遇到问题，重新构建镜像：

```bash
docker-compose down --rmi local
docker-compose build --no-cache ai-api ai-worker
docker-compose up -d
```

### 查看日志

```bash
docker-compose logs -f
docker-compose logs -f ai-api
docker-compose logs -f ai-worker
```

## 更多文档

- [模型下载指南](docs/manual-model-download.md)
- [本地模型 vs 外部模型](docs/local-vs-external-models.md)

## API 文档

启动服务后访问：http://localhost:7125/docs
