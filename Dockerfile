FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . /app
ENV FLASK_APP=app.py
ENV FLASK_ENV=production
EXPOSE 5000
# Serve via a production WSGI server (gunicorn), not the Werkzeug debug server.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "3", "app:create_app()"]
