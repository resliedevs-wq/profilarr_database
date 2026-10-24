FROM python:3.12-slim
WORKDIR /app
COPY evidence.py feed_adapter.py policy.json ./
USER 65534:65534
EXPOSE 9697
CMD ["python", "-B", "feed_adapter.py"]
