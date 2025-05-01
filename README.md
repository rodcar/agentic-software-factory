# Agentic Software Factory

This repository contains various components for an agentic software development platform, including code agents, Azure Functions, and MCP (Model Context Protocol) servers.

## Repository Structure

### `/code-agents`
Tools and agents for code generation and analysis:
- **claude_code_docker_env**: Docker environment for Claude code models
- **codex**: Docker-based code execution environment

### `/agentic-systems`
Agent-based systems and research:
- **sk-multi-agent-collaborative-project-specification**: Semantic Kernel-based collaborative agent system
- **azure-function-issue-research**: Research on Azure Functions issues and solutions

### `/azure-functions`
Azure Function components:
- **azure-function-code-job**: Azure Function for managing code jobs
- **azure-function-az-devops-webhook**: Azure Function for handling Azure DevOps webhooks

### `/mcp-servers`
Model Context Protocol servers:
- **sk-devops-agent-mcp**: Semantic Kernel DevOps agent using MCP
- **sk-job-launcher-mcp**: Server for launching code jobs in Azure DevOps using Semantic Kernel

## Getting Started

Each subfolder contains its own documentation and installation instructions. Please refer to the README.md in each project directory for specific setup and usage instructions.

## Requirements

- Python 3.8+
- Docker
- Azure subscription (for Azure Functions)
- Azure DevOps organization (for DevOps integrations)

## License

This project is licensed under the MIT License - see the individual project folders for details. 