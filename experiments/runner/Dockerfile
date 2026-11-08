# Image for experiments.run_isolated: Python with the agent's only third-party dependency.
# The project code is bind-mounted read-only at run time; nothing from a package is installed or run.
FROM python:3.12-slim
RUN pip install --no-cache-dir pydantic==2.13.2 \
    && useradd -u 10001 -m runner
USER 10001:10001
