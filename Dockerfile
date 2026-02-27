FROM 1186258278/openclaw-zh:latest

# 切换为 root 安装系统依赖
USER root

# 因为该镜像是 Debian 12 (bookworm) 且自带 node，我们为其补齐 python3
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 设置工作目录，假设拷贝到 /easyclaw 以防止与 /app 冲突 (如果是 node 的)
WORKDIR /easyclaw
COPY . /easyclaw

# 清理当前可能存在的沙箱与 __pycache__
RUN rm -rf sandbox/ __pycache__/ .venv/

# 使用 pip 加载依赖，由于 Debian 12 默认采用 PEP 668 环境隔离限制，所以加 --break-system-packages 或者用 venv
RUN python3 -m pip install --no-cache-dir fastapi uvicorn rich questionary --break-system-packages

ENV EASYCLAW_SANDBOX=1
ENV OPENCLAW_BIN=/usr/local/bin/openclaw

# 覆盖原底包 ENTRYPOINT
ENTRYPOINT []

CMD ["python3", "easyclaw.py", "tui"]
