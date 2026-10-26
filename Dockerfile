FROM python:3.12-slim
RUN useradd -m -u 1000 user
WORKDIR /app
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=user src ./src
COPY --chown=user web ./web
COPY --chown=user data ./data
ENV PYTHONPATH=/app/src
USER user
EXPOSE 7860
CMD ["python", "-m", "uvicorn", "matchroom.api:app", "--host", "0.0.0.0", "--port", "7860"]