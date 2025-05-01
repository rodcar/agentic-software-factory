# Start with a base Python image
FROM python:3.11-slim

# Set the working directory inside the container
WORKDIR /app

# Create .claude/commands directory
RUN mkdir -p .claude/commands

# Copy files from commands directory to .claude/commands
COPY commands/ .claude/commands/

# Copy azure-pipelines.yml to the container
COPY pipelines/azure-pipelines.yml /app/azure-pipelines.yml

# Install required dependencies (curl, git, ripgrep, and nodejs)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    git \
    ripgrep \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js (for Claude, if needed, or any other runtime)
RUN curl -fsSL https://deb.nodesource.com/setup_18.x | bash - && \
    apt-get install -y nodejs

# Install Claude Code (using npm)
RUN npm install -g @anthropic-ai/claude-code

# Create a non-root user (e.g., claudeuser) and switch to that user
RUN useradd -m claudeuser

# Copy your Python script into the container
COPY claude_job.py /app/

# Copy .claude.json into the home directory of the container
COPY .claude.json /home/claudeuser/.claude.json

# Copy the docker-entrypoint.sh script into the container and make it executable
COPY docker-entrypoint.sh /app/
RUN chmod +x /app/docker-entrypoint.sh

# Set permissions BEFORE changing user
RUN chmod +x /app/docker-entrypoint.sh && \
    chown -R claudeuser:claudeuser /app /home/claudeuser

# Switch to the non-root user
USER claudeuser

# Set the entrypoint to your job handler script
ENTRYPOINT ["./docker-entrypoint.sh"]