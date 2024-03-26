FROM python:3.11.8-slim-bullseye AS compile-image

# Apply security upgrades, install some nice to have and clean up afterwards
# Clean up after installing packages:
RUN export DEBIAN_FRONTEND=noninteractive && \
    apt-get update && \
    apt-get -y upgrade && \
    apt-get install -y --no-install-recommends gcc build-essential tini procps net-tools

# Create a venv
RUN python -m venv /opt/venv
# Make sure we use the virtualenv:
ENV PATH="/opt/venv/bin:$PATH"

# Copy in your requirements files
ADD requirements /requirements

# Install dependecies in the venv
RUN pip3 install --upgrade pip
RUN pip3 install -r requirements/production.txt

# Compile image has now installed a full virtual environment that we can copy to the
# build image

FROM python:3.11.8-slim-bullseye AS build-image

# Apply security upgrades, install some nice to have and clean up afterwards
RUN export DEBIAN_FRONTEND=noninteractive && \
    apt-get update && \
    apt-get -y upgrade && \
    apt-get install -y --no-install-recommends tini procps net-tools && \
    apt-get -y clean && \
    rm -rf /var/lib/apt/lists/*

# Copy in the venv from the compile image
COPY --from=compile-image /opt/venv /opt/venv

# Use the venv copied over
ENV PATH="/opt/venv/bin:$PATH"


# Copy your application code to the container (make sure you create a .dockerignore file if any large files or directories should be excluded)
RUN mkdir /app/
WORKDIR /app/
ADD . /app/

ENV PYTHONUNBUFFERED 1
ENV PYTHONFAULTHANDLER=1


# Don't run as root!
RUN useradd --create-home elgas-server-user
USER elgas-server-user

CMD python elgas_server/server.py --host=0.0.0.0 --port=8649



