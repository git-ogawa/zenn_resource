#!/bin/bash
set -ue

repository_url=$1
branch=$2
username=$3
password=$4
tls_verify=$5

repository_url="https://${username}:${password}@${repository_url#https://}"
last_element=$(basename "$repository_url")
destination=$(echo "$last_element" | sed 's/\.git$//')

if [[ ${tls_verify} == "false" ]]; then
    git config --global http.sslVerify false
fi

# Remove the previous directory
share_dir=/opt/stackstorm/virtualenvs/tmp
rm -rf ${share_dir}/${destination}

# Run git clone
git clone \
    ${repository_url} \
    -b ${branch} \
    ${share_dir}/${destination}
