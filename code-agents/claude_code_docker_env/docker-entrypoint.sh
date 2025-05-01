#!/bin/bash

# Check for required environment variables
if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "Error: ANTHROPIC_API_KEY environment variable is not set!"
    exit 1
fi

if [ -z "$REPOSITORY_URL" ]; then
    echo "Error: REPOSITORY_URL environment variable is not set!"
    exit 1
fi

# Parse the prompt passed as environment variable or argument
if [ -z "$PROMPT" ]; then
    echo "No prompt provided!"
    exit 1
fi

# Clone the repository
echo "Cloning repository: $REPOSITORY_URL"
git clone "$REPOSITORY_URL" /app/repo
if [ $? -ne 0 ]; then
    echo "Error: Failed to clone repository"
    #exit 1
    mkdir -p /app/repo
    cd /app/repo
    git config --global init.defaultBranch main
    git init
    git remote add origin "$REPOSITORY_URL"
fi

# Configure Git user
git config --local user.email "claude@anthropic.com"
git config --local user.name "Claude Code"
echo "Git user configured."

# Change to the repository directory
cd /app/repo

# Copy azure-pipelines.yml to the repository directory
if [ -f "/app/azure-pipelines.yml" ]; then
    echo "Copying azure-pipelines.yml to repository"
    cp /app/azure-pipelines.yml .
else
    echo "Warning: azure-pipelines.yml not found in /app directory"
fi

# Modify docker-entrypoint.sh to copy commands to the repo directory
mkdir -p .claude/commands
cp /app/.claude/commands/* .claude/commands/

# Then make sure your PROMPT starts with "/project:example"

# Print received prompt
echo "Running task with prompt: $PROMPT"

# Run Claude Code (substitute this with the actual command for Claude execution)
claude --json --verbose --allowedTools "Bash,FileCreation,FileEdit" --dangerously-skip-permissions -p "$PROMPT"

# Print completion message and explicitly kill the main process
echo "Task completed. Finalizing container."
# Force the container to stop by killing the main process
kill -9 1
