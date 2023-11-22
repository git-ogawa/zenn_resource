ARG ST2_VERSION
# FROM stackstorm/st2:${ST2_VERSION}
FROM st2-base
LABEL com.stackstorm.component="st2actionrunner"

# Install utils used by st2 'linux' pack, part of StackStorm core
RUN dnf install -y rsync \
  traceroute \
  net-tools \
  dnsutils \
  sendmail

# Install buildah
RUN dnf install -y vim buildah

USER root

VOLUME ["/home/stanley/.ssh", "/opt/stackstorm/packs", "/opt/stackstorm/virtualenvs"]
CMD ["/opt/stackstorm/st2/bin/st2actionrunner", "--config-file=/etc/st2/st2.conf", "--config-file=/etc/st2/st2.docker.conf", "--config-file=/etc/st2/st2.user.conf"]
