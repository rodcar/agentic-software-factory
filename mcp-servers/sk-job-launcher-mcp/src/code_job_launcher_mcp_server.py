import os
import base64
import time
import requests
import json
from dotenv import load_dotenv
from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion
from semantic_kernel.functions import kernel_function
from semantic_kernel.prompt_template import InputVariable, PromptTemplateConfig
import uvicorn
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.routing import Mount, Route
from typing import List
from pydantic import BaseModel

# Load environment variables
def load_environment():
    load_dotenv()
    return int(os.getenv("PORT", 5051))

# Initialize kernel and services
def create_kernel():
    kernel = Kernel()

    #kernel.add_service(OpenAIChatCompletion(service_id="default"))
    kernel.add_function(
        plugin_name="code_job_launcher",
        function_name="launch_code_job",
        function=launch_code_job,
        description="Create a new job in Azure DevOps using the provided PAT, organization URL, project name, and task."
    )

    return kernel

@kernel_function()
def launch_code_job(pat: str, org_url: str, project_name: str, functional_spec: str, test_plan: str, code_agent: str, job_type: str = "implementation") -> dict:
    """Create a new code job using the provided PAT, organization URL, project name, functional spec, test plan, and code agent."""
    print("Creating a new code job...")
    # print all args at once
    print(f"PAT: {pat}, Org URL: {org_url}, Project Name: {project_name}, Functional Spec: {functional_spec}, Test Plan: {test_plan}, Code Agent: {code_agent}")

    # Load CODE_JOB_URL from environment
    code_job_url = os.getenv("CODE_JOB_URL", "http://localhost:7071/api/code_job")
    
    # Prepare request payload
    payload = {
        "pat": pat,
        "org_url": org_url,
        "project_name": project_name,
        "functional_spec": functional_spec,
        "test_plan": test_plan,
        "code_agent": code_agent,
        "job_type": job_type
    }
    
    try:
        response = requests.post(
            code_job_url,
            headers={"Content-Type": "application/json"},
            data=json.dumps(payload),
            timeout=900  # 15 minutes timeout
        )
        response.raise_for_status()
        result = response.json()
        print(f"Azure function response: {result}")
    except Exception as e:
        return {"status": "error", "message": str(e)}

    return result

# Create Starlette app and routes
def create_app(server, sse):
    async def handle_sse(request):
        async with sse.connect_sse(request.scope, request.receive, request._send) as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    return Starlette(
        debug=True,
        routes=[
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=sse.handle_post_message),
        ],
    )

# Main entry point
def main():
    PORT = load_environment()
    kernel = create_kernel()
    server = kernel.as_mcp_server(server_name="sk")
    sse = SseServerTransport("/messages/")
    app = create_app(server, sse)
    uvicorn.run(app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    main()
