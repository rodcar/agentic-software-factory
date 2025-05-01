# MCP (Model Context Protocol) SSE Server

This project provides a simple implementation of an MCP (Model Context Protocol) server using Server-Sent Events (SSE) with Python.

## Features
- Exposes an SSE endpoint for real-time communication.
- Loads configuration (such as port) from a `.env` file.
- Easily extensible with plugins (see `plugins/` directory).

## Prerequisites
- Python 3.10+
- [pip](https://pip.pypa.io/en/stable/)

## Setup

1. **Clone the repository**

```bash
git clone <your-repo-url>
cd sk-devops-agent-mcp
```

2. **Install dependencies**

```bash
pip install -r requirements.txt
```

3. **Configure environment variables**

Create or edit the `.env` file to set the desired port (default is 5050):

```
PORT=5050
```

## Running the MCP SSE Server

```bash
python azure_devops_mcp_server.py
```

The server will start and listen on the port specified in your `.env` file (default: 5050).

## Using the SSE Endpoint

- The SSE endpoint is available at:

```
http://localhost:<PORT>/sse
```

- You can connect to this endpoint using any SSE-compatible client (such as EventSource in JavaScript).

### Example (JavaScript)

```js
const evtSource = new EventSource('http://localhost:5050/sse');
evtSource.onmessage = function(event) {
    console.log('New message:', event.data);
};
```

## Plugins

Plugins can be added in the `plugins/` directory. See the `plugins/azure_devops/` folder for an example structure.

## Development
- To add new functionality, extend the server or add new plugins.
- Restart the server after making code changes.

## Testing

Test scripts can be found in the `test/` directory. To run tests:

```bash
pytest test/
```

## License
MIT
