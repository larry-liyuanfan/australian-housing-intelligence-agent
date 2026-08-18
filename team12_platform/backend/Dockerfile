FROM python:3.12-slim

WORKDIR /app

# Keep Python logs visible in Kubernetes and avoid writing pyc files into the
# container layer.
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=9090

# Install backend dependencies before copying the full source tree so Docker can
# reuse the package-install layer when only application code changes.
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend /app/backend

EXPOSE 9090

# Start the Flask API package used by the notebook and Kubernetes probes.
CMD ["python", "-m", "backend.api.app"]
