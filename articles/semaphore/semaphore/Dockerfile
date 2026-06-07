FROM semaphoreui/semaphore:latest

USER root
COPY rootca.crt /usr/local/share/ca-certificates/rootca.crt
RUN apk add --no-cache ca-certificates && update-ca-certificates
USER 1001
