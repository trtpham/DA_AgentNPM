FROM node:22-bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends strace \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -u 10001 -m -d /home/agent agent
COPY canary/ /opt/canary/
COPY run_install.sh /usr/local/bin/run_install.sh
RUN chmod 755 /usr/local/bin/run_install.sh
USER 10001:10001
ENV HOME=/home/agent
