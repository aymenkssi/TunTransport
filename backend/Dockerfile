FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py auth.py database.py network.py trips.py routing.py places.py roads.py suggestions.py geocoder.py trust.py admin.py custom_lines.py notify.py geo.py matching.py vehicles.py admin.html ./

RUN useradd --create-home --uid 10001 app
USER app

EXPOSE 8001
# API_WORKERS processus (3 par défaut) : un par cœur utilisé ; ils se synchronisent (voir server.py).
CMD ["sh", "-c", "exec uvicorn server:app --host 0.0.0.0 --port 8001 --proxy-headers --forwarded-allow-ips '*' --workers ${API_WORKERS:-3}"]
