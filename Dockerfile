FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 18820
# A cloud deploy passes the team's configuration (LEAFMESH_TEAM_CONFIG_GZ,
# gzip + base64): it is loaded into the store only while the store is empty,
# then the agency starts. Locally `create-leafmesh --start` loads it instead.
CMD ["sh", "-c", "if [ -n \"$LEAFMESH_TEAM_CONFIG_GZ\" ]; then printf '%s' \"$LEAFMESH_TEAM_CONFIG_GZ\" | base64 -d | gunzip | leafmesh config import --if-empty - || exit 1; fi; exec python main.py"]
