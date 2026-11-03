FROM python:3.12-slim
RUN pip install --no-cache-dir guarddog==2.6.0 \
    && useradd -u 10001 -m -d /home/scan scan
ENV HOME=/tmp SEMGREP_ENABLE_VERSION_CHECK=0 SEMGREP_SEND_METRICS=off
USER 10001:10001
ENTRYPOINT ["guarddog"]
