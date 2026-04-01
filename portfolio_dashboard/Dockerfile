ARG BUILD_FROM=python:3.12-slim
FROM ${BUILD_FROM}

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl jq && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY dashboard/ ./dashboard/
COPY run.sh /run.sh
RUN chmod +x /run.sh

ENTRYPOINT ["/run.sh"]
