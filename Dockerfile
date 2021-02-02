FROM python:3.8
ARG UID=40000
ENV myWORKDIR /opt/synapse
# Add a work directory
WORKDIR ${myWORKDIR}
# Add user
RUN set -eu \
  ;adduser --home ${myWORKDIR} --no-create-home --uid ${UID} --disabled-password --disabled-login --shell /bin/sh abc -quiet \
  ;chown abc. ${myWORKDIR} \
  ;

# Switch to non privileged user
USER abc

# Copy the files from outside directory into the container image
COPY requirements.txt requirements.txt

# Install python virtual environment
# VIRUTAL_ENV is required see https://pythonspeed.com/articles/activate-virtualenv-dockerfile/
ENV VIRTUAL_ENV=${myWORKDIR}/venv
RUN set -eu \
  ;python3 -m venv ${VIRTUAL_ENV} \
  ;
# Set required environment variables
ENV PATH ${VIRTUAL_ENV}/bin:$PATH
# Install python dependencies into virtual environment
RUN set -eu \
  ;pip3 install --no-cache-dir -r requirements.txt \
  ;

# Add S6 Overlay
USER root
ADD https://github.com/just-containers/s6-overlay/releases/latest/download/s6-overlay-amd64.tar.gz /tmp/
RUN set -eu \
    ;tar xzf /tmp/s6-overlay-amd64.tar.gz -C / \
    ;

#COPY s6/permissions /etc/fix-attrs.d/00-synapse-set-permissions
COPY .docker/s6/prepare /etc/cont-init.d/00-synapse-prepare
COPY .docker/s6/run /etc/services.d/synapse/run

ENTRYPOINT ["/init"]
HEALTHCHECK --interval=60s --timeout=30s --start-period=60s --retries=3 CMD curl --fail http://127.0.0.1:5000/version || exit 1

# Expose the default port 5000
EXPOSE 5000

# Copy the files from outside directory into the container image
COPY --chown=abc:abc . .
