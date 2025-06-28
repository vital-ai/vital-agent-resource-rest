# vital-agent-resource-rest


# aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 924974635764.dkr.ecr.us-east-1.amazonaws.com

# docker buildx build --platform linux/arm64 -t vital-agent-resource-rest:latest .
# docker tag vital-agent-resource-rest:latest 924974635764.dkr.ecr.us-east-1.amazonaws.com/vital-agent-resource-rest:latest
# docker push 924974635764.dkr.ecr.us-east-1.amazonaws.com/vital-agent-resource-rest:latest

# aws --profile hadfield ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 487727733121.dkr.ecr.us-east-1.amazonaws.com

# docker buildx build --platform linux/arm64 -t vital-agent-resource-rest:latest .
# docker tag vital-agent-resource-rest:latest 487727733121.dkr.ecr.us-east-1.amazonaws.com/vital-agent-resource-rest:latest
# docker push 487727733121.dkr.ecr.us-east-1.amazonaws.com/vital-agent-resource-rest:latest
