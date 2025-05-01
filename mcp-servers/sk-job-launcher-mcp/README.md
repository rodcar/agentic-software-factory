# SK Job Launcher MCP

A Python server for launching code jobs in Azure DevOps using Semantic Kernel and MCP (Model Context Protocol).

## Features
- Launches jobs in Azure DevOps via REST API
- Uses Semantic Kernel for AI integration
- SSE (Server-Sent Events) support
- Starlette web server with Uvicorn

## Requirements
- Python 3.8+
- Azure DevOps Personal Access Token (PAT)

## Project Structure
```
├── src/
│   └── code_job_launcher_mcp_server.py   # Main server code
├── requirements.txt                     # Python dependencies
├── .gitignore                           # Git ignore rules
├── README.md                            # Project documentation
```

## Installation
1. Clone this repository.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Create a `.env` file with the following content:
   ```env
   PORT=5051
   ```

## Usage
Run the server:
```bash
python src/code_job_launcher_mcp_server.py
```

The server will start on the port specified in `.env` (default: 5051).

## Environment Variables
- `PORT`: Port to run the server (default: 5051)

## Best Practices
- Keep source code in `src/`.
- Use a `.env` file for configuration.
- Exclude unnecessary files using `.gitignore`.

## Author
- Ivan

## License
MIT
