FROM alpine:3.7
MAINTAINER Hypothes.is Project and contributors

# Install system build and runtime dependencies.
RUN apk add --no-cache \
    ca-certificates \
    python3

# Create the hypothesis user, group, home directory and package directory.
RUN addgroup -S hypothesis && adduser -S -G hypothesis -h /var/lib/hypothesis hypothesis
WORKDIR /var/lib/hypothesis

# Copy minimal data to allow installation of dependencies.
COPY requirements.txt ./

# Install build deps, build, and then clean up.
RUN apk add --no-cache --virtual build-deps \
    build-base \
    python3-dev \
  && pip3 install --no-cache-dir -U pip\
  && pip3 install --no-cache-dir -r requirements.txt \
  && apk del build-deps

# Copy the rest of the application files.
COPY Procfile Procfile
COPY ./badger ./badger

# If we're building from a git clone, ensure that .git is writeable
RUN [ -d .git ] && chown -R hypothesis:hypothesis .git || :

# Expose the web app's port.
EXPOSE 8001

# Set the application environment.
ENV PATH /var/lib/hypothesis/bin:$PATH
ENV PYTHONPATH /var/lib/hypothesis:$PYTHONPATH
RUN ln -sf /usr/bin/python3 /usr/bin/python

# Make output from honcho immediately visible.
ENV PYTHONUNBUFFERED 1

# Start the web server and indexing process.
USER hypothesis
CMD ["honcho", "start"]
