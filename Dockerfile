FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn
COPY . .
ENV KIZA_JOBS=1 PORT=5000
CMD ["gunicorn","-w","1","-b","0.0.0.0:5000","app:app"]
