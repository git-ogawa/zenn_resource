#!/bin/bash
set -ue

IMAGE_NAME=$1
IMAGE_TAG=$2
DIRECTORY=$3
DOCKERFILE_NAME=$4
REGISTRY_HOST=$5
TLS_VERIFY=$6


buildah build \
    -t ${IMAGE_NAME}:${IMAGE_TAG} \
    -f ${DIRECTORY}/${DOCKERFILE_NAME}

buildah tag ${IMAGE_NAME}:${IMAGE_TAG} ${REGISTRY_HOST}/${IMAGE_NAME}:${IMAGE_TAG}

buildah push \
    --tls-verify=${TLS_VERIFY} \
    ${REGISTRY_HOST}/${IMAGE_NAME}:${IMAGE_TAG}
