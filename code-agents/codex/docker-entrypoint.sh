#!/bin/bash
set -e  # Exit immediately if a command exits with a non-zero status

echo "Entrypoint script started"
echo "QUERY=${QUERY:-none}"
echo "REPOSITORY_URL=${REPOSITORY_URL:-none}"

# Set default branch to main
#git config --global init.defaultBranch main
# Configure git user for Codex
#git config --global user.name "Codex"
#git config --global user.email "codex@openai.com"

# Handle repository setup if URL provided
if [ -n "$REPOSITORY_URL" ]; then
  echo "Setting up repository from $REPOSITORY_URL"
  # Clean the directory first (except git folder)
  find . -mindepth 1 -maxdepth 1 -not -name ".git" -exec rm -rf {} \; 2>/dev/null || true
  
  # Try to clone the repository
  if git clone "$REPOSITORY_URL" . 2>/dev/null; then
    echo "Repository cloned successfully"
  else
    echo "Failed to clone repository. Initializing new repository."
    git init
    
    # If we have a URL, try to set it as remote
    if [ -n "$REPOSITORY_URL" ]; then
      git remote add origin "$REPOSITORY_URL"
      echo "Initialized new repository with remote $REPOSITORY_URL"
    else
      echo "Initialized new empty repository"
    fi
  fi
else
  # If no repository URL is provided, make sure we have a git repo
  if [ ! -d ".git" ]; then
    echo "No repository URL provided, initializing new repository"
    git init
  fi
fi

# Run Codex with query
if [ -n "$QUERY" ]; then
  echo "Running codex with query: $QUERY"
  codex --approval-mode full-auto --json -q "$QUERY"
else
  echo "Running codex with command line arguments"
  codex --approval-mode full-auto --json -q "$@"
fi 

# Keep container running if KEEP_RUNNING is set
if [ "${KEEP_RUNNING:-false}" = "true" ]; then
  echo "Container task complete. Keeping container running as requested."
  # Use tail -f /dev/null to keep the container running
  exec tail -f /dev/null
else
  echo "Container task complete. Container will exit now."
fi 