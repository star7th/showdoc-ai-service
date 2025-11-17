# 手动下载 BGE 模型指南

## 重要提示

**本服务仅支持手动下载模型，不会自动下载。** 在构建 Docker 镜像或运行服务之前，必须先手动下载模型文件。

**网络访问说明**：
- Hugging Face 官方网站在中国大陆无法直接访问
- 需要使用代理或其他方式访问海外网络
- 镜像站点不稳定，不推荐使用
- 请用户自行解决网络访问问题

## 模型信息

- **模型名称**: `BAAI/bge-base-zh-v1.5`
- **模型大小**: 约 400-500 MB
- **官方页面**: https://huggingface.co/BAAI/bge-base-zh-v1.5

## 下载方式

### 方式一：使用 Hugging Face 官方源（需要访问海外网络）

**模型页面**: https://huggingface.co/BAAI/bge-base-zh-v1.5

**注意**: 在中国大陆需要使用代理或其他方式访问。

### 方式二：使用镜像站点（不推荐，不稳定）

**镜像站点**: https://hf-mirror.com

**模型页面**: https://hf-mirror.com/BAAI/bge-base-zh-v1.5

**注意**: 镜像站点可能不稳定或无法访问，建议优先使用官方源。

## 需要下载的文件列表

### 必需文件（必须下载）:

1. **config.json** - 模型配置文件
2. **pytorch_model.bin** - PyTorch 模型权重文件（最大，约 400MB）
3. **tokenizer.json** - Tokenizer 配置文件
4. **tokenizer_config.json** - Tokenizer 配置
5. **vocab.txt** - 词汇表文件
6. **sentence_bert_config.json** - Sentence-BERT 配置
7. **modules.json** - 模块配置
8. **config_sentence_transformers.json** - Sentence Transformers 配置
9. **special_tokens_map.json** - 特殊 token 映射
10. **1_Pooling/config.json** - Pooling 层配置（在 `1_Pooling` 文件夹中）

### 可选文件:

- `README.md` - 模型说明文档
- `gitattributes` - Git 属性文件

## 放置目录结构

### 标准目录结构（必须）

将下载的文件按照以下结构放置在项目根目录下：

```
项目根目录/
└── models/
    └── bge-base-zh-v1.5/
        ├── config.json
        ├── pytorch_model.bin          # 约 400MB
        ├── tokenizer.json
        ├── tokenizer_config.json
        ├── vocab.txt
        ├── sentence_bert_config.json
        ├── modules.json
        ├── config_sentence_transformers.json
        ├── special_tokens_map.json
        ├── README.md                   # 可选
        └── 1_Pooling/
            └── config.json
```

### 目录说明

- **项目根目录**: 即 `showdoc-ai-service/` 目录
- **模型目录**: `models/bge-base-zh-v1.5/`（注意：目录名是 `bge-base-zh-v1.5`，不是 `BAAI/bge-base-zh-v1.5`）

## 下载步骤

### 方法一：使用 Git LFS（推荐）

如果已安装 Git 和 Git LFS：

```bash
# 进入项目根目录
cd showdoc-ai-service

# 创建模型目录
mkdir -p models

# 克隆模型仓库（使用镜像，速度快）
cd models
git clone https://hf-mirror.com/BAAI/bge-base-zh-v1.5

# 或使用官方源
# git clone https://huggingface.co/BAAI/bge-base-zh-v1.5

# 重命名目录（如果需要）
# mv BAAI-bge-base-zh-v1.5 bge-base-zh-v1.5
```

**注意**: 如果使用 Git 克隆，目录名可能是 `BAAI-bge-base-zh-v1.5`，需要重命名为 `bge-base-zh-v1.5`。

### 方法二：手动下载文件

#### Windows PowerShell 脚本

```powershell
# 进入项目根目录
cd D:\workplace\showdoc-ai-service

# 创建模型目录
New-Item -ItemType Directory -Force -Path "models\bge-base-zh-v1.5"
New-Item -ItemType Directory -Force -Path "models\bge-base-zh-v1.5\1_Pooling"

# 设置变量
# 注意：镜像站点不稳定，建议使用官方源（需要代理）
$baseUrl = "https://huggingface.co"  # 或使用 "https://hf-mirror.com"（不推荐，不稳定）
$modelDir = "models\bge-base-zh-v1.5"

# 必需文件列表
$files = @(
    "config.json",
    "pytorch_model.bin",
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.txt",
    "sentence_bert_config.json",
    "modules.json",
    "config_sentence_transformers.json",
    "special_tokens_map.json",
    "1_Pooling/config.json"
)

# 下载文件
foreach ($file in $files) {
    $url = "$baseUrl/BAAI/bge-base-zh-v1.5/resolve/main/$file"
    $outputPath = "$modelDir\$file"
    Write-Host "下载: $file" -ForegroundColor Cyan
    try {
        Invoke-WebRequest -Uri $url -OutFile $outputPath -ErrorAction Stop
        $size = (Get-Item $outputPath).Length / 1MB
        Write-Host "✅ 完成: $file ($([math]::Round($size, 2)) MB)" -ForegroundColor Green
    } catch {
        Write-Host "❌ 失败: $file - $_" -ForegroundColor Red
    }
}

Write-Host "`n下载完成！请检查文件是否完整。" -ForegroundColor Yellow
```

#### Linux/Mac Bash 脚本

```bash
#!/bin/bash
# 进入项目根目录
cd showdoc-ai-service

# 创建模型目录
mkdir -p models/bge-base-zh-v1.5/1_Pooling

# 设置变量
# 注意：镜像站点不稳定，建议使用官方源（需要代理）
BASE_URL="https://huggingface.co"  # 或使用 "https://hf-mirror.com"（不推荐，不稳定）
MODEL_DIR="models/bge-base-zh-v1.5"

# 必需文件列表
files=(
    "config.json"
    "pytorch_model.bin"
    "tokenizer.json"
    "tokenizer_config.json"
    "vocab.txt"
    "sentence_bert_config.json"
    "modules.json"
    "config_sentence_transformers.json"
    "special_tokens_map.json"
    "1_Pooling/config.json"
)

# 下载文件
for file in "${files[@]}"; do
    url="${BASE_URL}/BAAI/bge-base-zh-v1.5/resolve/main/${file}"
    output_path="${MODEL_DIR}/${file}"
    echo "下载: ${file}"
    if curl -L -o "${output_path}" "${url}"; then
        size=$(du -h "${output_path}" | cut -f1)
        echo "✅ 完成: ${file} (${size})"
    else
        echo "❌ 失败: ${file}"
    fi
done

echo ""
echo "下载完成！请检查文件是否完整。"
```

### 方法三：使用浏览器下载

1. 使用代理访问模型页面：https://huggingface.co/BAAI/bge-base-zh-v1.5
   - **注意**: 在中国大陆无法直接访问，需要使用代理或其他方式
2. 点击 "Files and versions" 标签页
3. 逐个下载必需文件到 `models/bge-base-zh-v1.5/` 目录
4. 下载 `1_Pooling/config.json` 到 `models/bge-base-zh-v1.5/1_Pooling/` 目录

## 验证下载

### 检查文件完整性

确保以下文件存在且大小正确：

```bash
# Windows PowerShell
Get-ChildItem models\bge-base-zh-v1.5\*.json, models\bge-base-zh-v1.5\*.bin | Format-Table Name, @{Label="Size(MB)";Expression={[math]::Round($_.Length/1MB, 2)}}

# Linux/Mac
ls -lh models/bge-base-zh-v1.5/*.json models/bge-base-zh-v1.5/*.bin
```

**关键文件大小参考**:
- `pytorch_model.bin`: 约 400-450 MB
- `config.json`: 几 KB
- `tokenizer.json`: 几 MB
- 其他文件: 几 KB 到几 MB

### Python 验证脚本

创建 `verify_model.py`:

```python
#!/usr/bin/env python3
"""验证模型文件是否完整"""
import os

model_dir = "models/bge-base-zh-v1.5"
required_files = [
    "config.json",
    "pytorch_model.bin",
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.txt",
    "sentence_bert_config.json",
    "modules.json",
    "config_sentence_transformers.json",
    "special_tokens_map.json",
    "1_Pooling/config.json"
]

print(f"检查模型目录: {model_dir}")
print("=" * 50)

all_ok = True
for file in required_files:
    file_path = os.path.join(model_dir, file)
    if os.path.exists(file_path):
        size = os.path.getsize(file_path) / 1024 / 1024
        print(f"✅ {file:40s} ({size:8.2f} MB)")
    else:
        print(f"❌ {file:40s} (缺失)")
        all_ok = False

print("=" * 50)
if all_ok:
    print("✅ 所有必需文件都存在！")
    
    # 尝试加载模型
    try:
        from sentence_transformers import SentenceTransformer
        print("\n尝试加载模型...")
        model = SentenceTransformer(model_dir, local_files_only=True)
        print("✅ 模型加载成功！")
        
        # 测试编码
        embedding = model.encode("测试文本", convert_to_numpy=True)
        print(f"✅ 编码测试成功，维度: {embedding.shape}")
    except Exception as e:
        print(f"⚠️ 模型加载失败: {e}")
else:
    print("❌ 部分文件缺失，请重新下载")
```

运行验证：

```bash
python verify_model.py
```

## Docker 构建

下载完成后，可以正常构建 Docker 镜像：

```bash
docker build -t showdoc-ai-service .
```

构建时会自动验证模型文件是否存在。

**注意**: 构建前必须确保模型文件已手动下载并放置在 `models/bge-base-zh-v1.5/` 目录下，否则构建会失败。

## 常见问题

### Q: 构建时提示模型目录不存在？

A: 确保模型文件已下载到 `models/bge-base-zh-v1.5/` 目录，且目录名正确（注意是 `bge-base-zh-v1.5`，不是 `BAAI-bge-base-zh-v1.5`）。

### Q: 构建时提示必需文件缺失？

A: 检查 `models/bge-base-zh-v1.5/` 目录下是否包含：
- `config.json`
- `pytorch_model.bin`
- `1_Pooling/config.json`

### Q: 无法访问 Hugging Face 官网怎么办？

A: 
- 在中国大陆需要使用代理或其他方式访问海外网络
- 请用户自行解决网络访问问题
- 镜像站点不稳定，不推荐使用

### Q: 下载速度慢怎么办？

A: 
- 使用代理访问 Hugging Face 官网
- 或尝试使用镜像站点（但不保证可用）

### Q: 可以使用其他目录吗？

A: 不可以。代码会自动检测 `models/bge-base-zh-v1.5/` 目录，必须使用这个路径。

### Q: 下载的文件不完整怎么办？

A: 重新下载缺失的文件，确保 `pytorch_model.bin` 文件大小约 400MB。

## 相关链接

- 模型官方页面: https://huggingface.co/BAAI/bge-base-zh-v1.5
- 镜像站点: https://hf-mirror.com/BAAI/bge-base-zh-v1.5
- FlagEmbedding 项目: https://github.com/FlagOpen/FlagEmbedding
