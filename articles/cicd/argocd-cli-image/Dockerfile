FROM ubuntu:latest

RUN apt-get update && apt-get install -y curl && \
    curl -L https://github.com/argoproj/argo-cd/releases/download/v2.8.0/argocd-linux-amd64 -o argocd && \
    chmod +x argocd && \
    mv argocd /usr/local/bin && \
    apt-get clean && rm -rf /var/lib/apt/lists/*
ENTRYPOINT ["argocd"]
