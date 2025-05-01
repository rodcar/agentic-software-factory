# Start with a base Node.js image
FROM node:20-slim

# Set the working directory inside the container
WORKDIR /app

# Install required dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    git \
    iproute2 \
    ipset \
    iptables \
    ripgrep \
    sudo \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set up environment variables
ENV NPM_CONFIG_PREFIX=/usr/local/share/npm-global
ENV PATH=$PATH:/usr/local/share/npm-global/bin

# Create npm global directory with correct permissions
RUN mkdir -p /usr/local/share/npm-global

# Create a non-root user
RUN useradd -m codexuser

# Copy your Codex package
COPY codex-cli/dist/codex.tgz /tmp/codex.tgz

# Add entrypoint script
COPY docker-entrypoint.sh /app/docker-entrypoint.sh

# Make entrypoint executable and set permissions
RUN chmod +x /app/docker-entrypoint.sh && \
    chown -R codexuser:codexuser /app /usr/local/share/npm-global

# Switch to non-root user
USER codexuser

# Install Codex globally
RUN npm install -g /tmp/codex.tgz

# Set the entrypoint to your script
ENTRYPOINT ["/app/docker-entrypoint.sh"]