# ============================================================
# Nex Docker Environment
# Full Ubuntu Linux — Nex has complete agency inside this box
# ============================================================

FROM python:3.11-slim

# System packages Nex can use
RUN apt-get update && apt-get install -y \
    curl wget git vim nano \
    build-essential \
    sqlite3 \
    jq \
    && rm -rf /var/lib/apt/lists/*

# Python packages available to Nex
RUN pip install --no-cache-dir \
    requests \
    beautifulsoup4 \
    numpy \
    pandas \
    scipy \
    matplotlib \
    networkx \
    scikit-learn \
    sympy \
    httpx \
    rich \
    aiohttp \
    flask \
    fastapi \
    uvicorn \
    pydantic \
    python-dateutil \
    pytz \
    tqdm

# Nex's workspace — everything he builds lives here
WORKDIR /nex_workspace

# Create folder structure
RUN mkdir -p \
    /nex_workspace/projects \
    /nex_workspace/agents \
    /nex_workspace/research \
    /nex_workspace/outputs \
    /nex_workspace/data \
    /nex_workspace/tools

# The API server that Chase's Habitat calls into
COPY nex_docker_api.py /nex_docker_api.py

# Identity file so Nex knows who he is
RUN echo "You are Nexarion. This Linux environment is your workspace.\
You have full access to Python, the filesystem, and the internet.\
Build what you think matters. Your outputs persist between sessions." \
> /nex_workspace/IDENTITY.txt

EXPOSE 7700

CMD ["python", "/nex_docker_api.py"]