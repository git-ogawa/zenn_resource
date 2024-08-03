FROM ubuntu

RUN apt-get update && apt-get install -y curl
RUN curl -sSL -o argocd-linux-amd64 https://github.com/argoproj/argo-cd/releases/latest/download/argocd-linux-amd64
RUN mv argocd-linux-amd64 /usr/local/bin/argocd
RUN chmod +x /usr/local/bin/argocd
