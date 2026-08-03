# 3.12, not 3.11: vital-ai-vitalsigns >=0.1.44 and kgraphservice >=0.0.8 declare
# requires_python >=3.12. On 3.11 pip can only reach old vitalsigns releases while
# vital-ai-domain 0.1.9 requires >=0.1.54, which is unresolvable. Matches the
# vital-agent-resource-rest conda env (3.12).
FROM python:3.12-slim

WORKDIR /usr/src/app

RUN apt-get update && apt-get install -y \
    build-essential \
    g++ \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /usr/src/app/

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /var/log/agentresourcerest

RUN chmod -R 755 /var/log/agentresourcerest

# Make port 8008 available to the world outside this container
EXPOSE 8008

CMD ["uvicorn", "vital_agent_resource_app.app:app", "--host", "0.0.0.0", "--port", "8008"]
