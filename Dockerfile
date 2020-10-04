FROM python:3-slim

# Add a work directory
WORKDIR /opt/synapse

# Copy the files from outside directory into the container image
COPY . .

# Install python dependencies
RUN set -eu \
  ;pip3 install --no-cache --no-cache-dir -r requirements.txt

# Expose the default port 5000
EXPOSE 5000

# Activate our "entrypoint script" app.py
ENTRYPOINT [ "./app.py"]
