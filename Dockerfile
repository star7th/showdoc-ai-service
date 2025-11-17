# ============================================
# 第一阶段：基础镜像（包含依赖和模型）
# 只有当 requirements.txt 或 models/ 改变时才需要重新构建
# ============================================
FROM python:3.12-slim AS base

WORKDIR /app

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV PIP_PROGRESS_BAR=off
# 禁用所有 BLAS/数学库的多线程，避免 pthread 问题
ENV OPENBLAS_NUM_THREADS=1
ENV OMP_NUM_THREADS=1
ENV MKL_NUM_THREADS=1
ENV NUMEXPR_NUM_THREADS=1
ENV VECLIB_MAXIMUM_THREADS=1
# 禁用 transformers 和 tokenizers 的多线程操作（避免 CentOS 7 等受限环境的线程创建失败）
ENV TOKENIZERS_PARALLELISM=false
ENV HF_HUB_DISABLE_PROGRESS_BARS=1
ENV TRANSFORMERS_NO_ADVISORY_WARNINGS=1
ENV HF_HUB_DOWNLOAD_TIMEOUT=300
# Python 优化：不生成 .pyc 文件（运行时不需要）
ENV PYTHONDONTWRITEBYTECODE=1

# 配置 pip 使用清华大学镜像源并更新 pip
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple && \
    pip config set global.trusted-host pypi.tuna.tsinghua.edu.cn && \
    pip install --no-cache-dir --upgrade pip

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖（合并命令以减少层数）
RUN pip install --no-cache-dir -r requirements.txt && \
    # 清理 pip 缓存和临时文件
    pip cache purge && \
    # 清理 Python 缓存文件（如果存在）
    find /usr/local/lib/python3.12 -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true && \
    find /usr/local/lib/python3.12 -type f -name "*.pyc" -delete 2>/dev/null || true && \
    find /usr/local/lib/python3.12 -type f -name "*.pyo" -delete 2>/dev/null || true && \
    # 清理不必要的测试和示例文件（保留运行时需要的文件）
    find /usr/local/lib/python3.12/site-packages -type d -name "tests" -exec rm -rf {} + 2>/dev/null || true && \
    find /usr/local/lib/python3.12/site-packages -type d -name "test" -exec rm -rf {} + 2>/dev/null || true && \
    find /usr/local/lib/python3.12/site-packages -type d -name "examples" -exec rm -rf {} + 2>/dev/null || true && \
    find /usr/local/lib/python3.12/site-packages -type d -name "example" -exec rm -rf {} + 2>/dev/null || true && \
    # 清理 torch 的测试和示例文件（torch 包很大，清理这些可以节省空间）
    find /usr/local/lib/python3.12/site-packages/torch -type d -name "test" -exec rm -rf {} + 2>/dev/null || true && \
    find /usr/local/lib/python3.12/site-packages/torch -type d -name "examples" -exec rm -rf {} + 2>/dev/null || true && \
    find /usr/local/lib/python3.12/site-packages/torch -type d -name "benchmark" -exec rm -rf {} + 2>/dev/null || true && \
    # 清理 transformers 的测试和示例文件
    find /usr/local/lib/python3.12/site-packages/transformers -type d -name "tests" -exec rm -rf {} + 2>/dev/null || true && \
    find /usr/local/lib/python3.12/site-packages/transformers -type d -name "examples" -exec rm -rf {} + 2>/dev/null || true && \
    # 清理 langchain 的测试和示例文件
    find /usr/local/lib/python3.12/site-packages/langchain -type d -name "tests" -exec rm -rf {} + 2>/dev/null || true && \
    find /usr/local/lib/python3.12/site-packages/langchain -type d -name "examples" -exec rm -rf {} + 2>/dev/null || true && \
    # 清理文档文件（保留运行时需要的文件）
    find /usr/local/lib/python3.12/site-packages -type f -name "*.md" -delete 2>/dev/null || true && \
    find /usr/local/lib/python3.12/site-packages -type f -name "*.rst" -delete 2>/dev/null || true && \
    find /usr/local/lib/python3.12/site-packages -type f -name "LICENSE*" -delete 2>/dev/null || true && \
    find /usr/local/lib/python3.12/site-packages -type f -name "CHANGELOG*" -delete 2>/dev/null || true && \
    find /usr/local/lib/python3.12/site-packages -type f -name "AUTHORS*" -delete 2>/dev/null || true && \
    find /usr/local/lib/python3.12/site-packages -type f -name "CONTRIBUTING*" -delete 2>/dev/null || true && \
    # 清理空目录
    find /usr/local/lib/python3.12 -type d -empty -delete 2>/dev/null || true && \
    echo "✅ 依赖安装和清理完成"

# 复制本地模型目录（必须手动下载）
# 注意：模型必须手动下载并放置在 models/bge-base-zh-v1.5/ 目录下
# 如果 models/ 目录不存在，构建会失败
# 下载指引请参考 docs/manual-model-download.md
COPY models/ models/

# 验证模型文件（必须手动下载）
# 模型必须手动下载并放置在 models/bge-base-zh-v1.5/ 目录下
RUN echo "=== 验证模型文件 ===" && \
    if [ -d models/bge-base-zh-v1.5 ] && [ "$(ls -A models/bge-base-zh-v1.5 2>/dev/null)" ]; then \
        echo "✅ 检测到模型目录: models/bge-base-zh-v1.5" && \
        if [ -f models/bge-base-zh-v1.5/config.json ] && [ -f models/bge-base-zh-v1.5/pytorch_model.bin ]; then \
            echo "✅ 模型必需文件存在" && \
            ls -lh models/bge-base-zh-v1.5/*.json models/bge-base-zh-v1.5/*.bin 2>/dev/null | head -5; \
        else \
            echo "❌ 模型必需文件缺失，请检查 models/bge-base-zh-v1.5/ 目录" && \
            echo "   必需文件: config.json, pytorch_model.bin" && \
            exit 1; \
        fi; \
    else \
        echo "❌ 模型目录不存在: models/bge-base-zh-v1.5" && \
        echo "   请手动下载模型并放置在 models/bge-base-zh-v1.5/ 目录下" && \
        echo "   下载指引: docs/manual-model-download.md" && \
        exit 1; \
    fi && \
    echo "=== 模型验证完成 ==="

# ============================================
# 第二阶段：最终镜像（基于基础镜像，只添加代码）
# 当代码改变时，只需要重新构建这一层，基础层会被缓存复用
# ============================================
FROM base AS final

# 复制应用代码（放在最后，避免代码改动导致重装依赖）
COPY app/ app/
COPY worker/ worker/

# 清理应用代码的缓存文件（如果存在）
RUN find /app -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true && \
    find /app -type f -name "*.pyc" -delete 2>/dev/null || true && \
    find /app -type f -name "*.pyo" -delete 2>/dev/null || true && \
    echo "✅ 应用代码清理完成"

# 暴露端口
EXPOSE 7125

# 启动命令
# 使用完整的应用（不再用最小化版本）
# 使用 --loop asyncio 避免 uvloop 在 CentOS 7 上的兼容性问题
# 使用 --log-level warning 精简日志输出，只显示警告和错误
# 使用 --workers 2 启动 2 个 worker 进程，提高并发处理能力
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7125", "--workers", "2", "--log-level", "warning", "--loop", "asyncio"]

