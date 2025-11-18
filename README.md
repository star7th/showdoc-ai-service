# ShowDoc AI 服务

ShowDoc AI 知识库的后端服务，提供文档索引、RAG 检索和智能问答功能。

## 关于本项目

本项目是 [ShowDoc](https://github.com/star7th/showdoc) 的 AI 功能扩展服务，采用**独立部署架构**：

### 技术栈

- **运行环境**: Python 3.10+
- **Web 框架**: FastAPI
- **向量数据库**: Qdrant
- **任务队列**: Celery + Redis
- **Embedding 模型**: BGE-base-zh-v1.5（本地部署）

## 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/star7th/showdoc-ai-service.git
cd showdoc-ai-service
```

### 2. 准备配置

```bash
# 复制环境变量配置
cp env.example .env
# 编辑 .env 文件，设置 SERVICE_TOKEN

# 复制 LLM 配置文件
cp config/llm.yaml.example config/llm.yaml
# 编辑 config/llm.yaml，配置你的 LLM API Key
```

### 3. 下载模型

**必须**：在构建 Docker 镜像之前，先手动下载模型文件到 `models/bge-base-zh-v1.5/` 目录。

详细步骤：参考 [模型下载指南](docs/manual-model-download.md)

### 4. 启动服务

```bash

#构建。构建过程中要下载几个G的依赖，可能要几分钟到半个小时
docker-compose build 

# 启动所有服务
docker-compose up -d

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f

# 验证服务
curl http://localhost:7125/api/health
```

### 把地址填写到showdoc管理后台

在showdoc管理后台填写本项目访问地址，同时填上.env环境变量里的认证token

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

###  启动失败

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

## 相关链接

- **ShowDoc 主项目**: https://github.com/star7th/showdoc
- **产品设计文档**: 查看 ShowDoc 主项目中的 `docs/ai-knowledge-base-design.md`
- **问题反馈**: 请在对应仓库提交 Issue
  - AI 服务相关问题 → 本仓库
  - ShowDoc 主功能问题 → [ShowDoc 主仓库](https://github.com/star7th/showdoc)
