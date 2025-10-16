# Docker Deployment Guide for LIMP

This guide explains how to containerize and deploy the LIMP application using Docker.

## Quick Start

### Development Environment

1. **Build a local impage:**
   ```sh
   docker build -t limp:latest .
   ```

2. **Run a local image:**
  ```sh
      docker run --rm \
      --name limp-app  \
      -p 8000:8000 \
      -v ./config-docker.yaml:/app/config.yaml:ro \
      -v ./limp.db:/app/limp.db \
      -e LIMP_CONFIG=config.yaml \
      limp:latest
  ```

## Configuration

### Environment Variables

LIMP resolves environment variables according to the following algorithm:

1. Check the environment
2. If not found, check the `.env` file
3. If not found, use the default value.

The most important configuration variable is `LIMP_CONFIG` that points
to the configuration file location.

LIMP containers support remote configuration. If the `LIMP_CONFIG` is an
`http://` or `https://` URL, the startup script will attempt to download the
configuration prior to starting the container.

## Database Options

### SQLite (Default for Development)
- No additional setup required
- Suitable for development and small deployments

### PostgreSQL (Production)

- Update your `config.yaml` database URL:
  ```yaml
  database:
    url: "postgresql://limp:${POSTGRES_PASSWORD}@postgres:5432/limp"
  ```

## Building and Running

### Build the Image
```bash
docker build -t limp:latest .
```

### Run Standalone Container
```bash
docker run -d \
  --name limp-app \
  -p 8000:8000 \
  -v $(pwd)/config.yaml:/app/config.yaml:ro \
  -v limp-data:/app/data \
  limp:latest
```

## Health Monitoring

The application includes health checks:

- **Endpoint**: `http://localhost:8000/health`
- **Interval**: 30 seconds
- **Timeout**: 10 seconds
- **Retries**: 3 attempts

## Security Considerations

- **Non-root user**: Application runs as `limp` user
- **Read-only config**: Configuration files mounted as read-only
- **Minimal base image**: Uses Python slim image
- **No unnecessary packages**: Multi-stage build removes build dependencies


