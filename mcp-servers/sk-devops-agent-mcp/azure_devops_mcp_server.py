import os
import base64
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

class TestCaseModel(BaseModel):
    title: str

# Load environment variables
def load_environment():
    load_dotenv()
    return int(os.getenv("PORT", 5050))

# Initialize kernel and services
def create_kernel():
    kernel = Kernel()

    kernel.add_service(OpenAIChatCompletion(service_id="default"))
    kernel.add_function(
        plugin_name="azure_devops",
        function_name="create_project",
        function=create_azure_devops_project,
        description="Create a new Azure DevOps project using the provided PAT and organization URL."
    )
    kernel.add_function(
        plugin_name="azure_devops",
        function_name="create_work_item",
        function=create_azure_devops_work_item,
        description="Create a new Azure DevOps work item (default type: Product Backlog Item) using the provided PAT, organization URL, project name, work item type, title, and description."
    )
    kernel.add_function(
        plugin_name="azure_devops",
        function_name="create_test_plan_with_cases",
        function=create_azure_devops_test_plan_with_cases,
        description="Create a test plan, suite, test cases, and add them to the suite in Azure DevOps."
    )
    kernel.add_function(
        plugin_name="azure_devops",
        function_name="find_code_agent_commit",
        function=find_code_agent_commit,
        description="Find the latest commit of the specified Azure DevOps project."
    )
    return kernel

@kernel_function()
def create_azure_devops_project(pat: str, org_url: str, project_name: str, project_description: str):
    """Create a new Azure DevOps project using the provided PAT and organization URL."""
    try:
        # Prepare REST API URL and headers
        organization_url = org_url.rstrip('/')
        url = f"{organization_url}/_apis/projects?api-version=7.1-preview.4"
        auth_string = f":{pat}"
        authorization = base64.b64encode(auth_string.encode('ascii')).decode('ascii')
        headers = {
            'Content-Type': 'application/json',
            'Authorization': 'Basic ' + authorization
        }

        # Prepare request body
        process_template_id = "6b724908-ef14-45cf-84f8-768b5384da45"  # Default Scrum process
        body = {
            "name": project_name,
            "description": project_description,
            "capabilities": {
                "versioncontrol": {"sourceControlType": "Git"},
                "processTemplate": {"templateTypeId": process_template_id}
            }
        }

        response = requests.post(url, headers=headers, json=body)

        if response.status_code == 202:
            operation_reference = response.json()
            project_url = f"{organization_url}/{project_name}"
            return {
                "operation_id": operation_reference.get("id"),
                "project_url": project_url,
                "message": f"Project '{project_name}' creation has started."
            }
        elif response.status_code == 401:
            return {"error": "Authentication failed. Please check your PAT and organization URL."}
        else:
            return {"error": f"Error: {response.status_code} {response.text}"}
    except Exception as e:
        return {"error": f"Failed to create project: {str(e)}"}

@kernel_function()
def create_azure_devops_work_item(
    pat: str,
    org_url: str,
    project_name: str,
    title: str,
    description: str,
    work_item_type: str = "Product Backlog Item"
):
    """Create a new Azure DevOps work item using the provided PAT, organization URL, project name, work item type, title, and description."""
    try:
        organization_url = org_url.rstrip('/')
        # URL encode the work item type for the REST API
        from urllib.parse import quote
        encoded_type = quote(work_item_type)
        url = f"{organization_url}/{project_name}/_apis/wit/workitems/${encoded_type}?api-version=7.1-preview.3"
        auth_string = f":{pat}"
        authorization = base64.b64encode(auth_string.encode('ascii')).decode('ascii')
        headers = {
            'Content-Type': 'application/json-patch+json',
            'Authorization': 'Basic ' + authorization
        }
        work_item_data = [
            {
                "op": "add",
                "path": "/fields/System.Title",
                "from": None,
                "value": title
            },
            {
                "op": "add",
                "path": "/fields/System.Description",
                "from": None,
                "value": description
            }
        ]
        response = requests.post(url, headers=headers, json=work_item_data)
        if response.status_code in (200, 201):
            work_item = response.json()
            return {
                "id": work_item.get("id"),
                "url": work_item.get("url"),
                "message": f"Work item '{title}' of type '{work_item_type}' created successfully."
            }
        elif response.status_code == 401:
            return {"error": "Authentication failed. Please check your PAT and organization URL."}
        else:
            return {"error": f"Error: {response.status_code} {response.text}"}
    except Exception as e:
        return {"error": f"Failed to create work item: {str(e)}"}

@kernel_function()
def create_azure_devops_test_plan_with_cases(
    pat: str,
    org_url: str,
    project_name: str,
    plan_name: str,
    plan_description: str,
    suite_name: str,
    test_cases: List[TestCaseModel]
):
    """Create a test plan, a static test suite, test cases, and add them to the suite in Azure DevOps."""
    try:
        organization_url = org_url.rstrip('/')
        # Auth header
        auth_string = f":{pat}"
        authorization = base64.b64encode(auth_string.encode('ascii')).decode('ascii')
        headers = {
            'Content-Type': 'application/json',
            'Authorization': 'Basic ' + authorization
        }
        # 1. Create test plan
        plan_body = {
            "name": plan_name,
            "description": plan_description
        }
        plan_url = f"{organization_url}/{project_name}/_apis/test/plans?api-version=5.0"
        plan_response = requests.post(plan_url, headers=headers, json=plan_body)
        if plan_response.status_code not in (200, 201):
            return {"error": f"Error creating test plan: {plan_response.status_code} {plan_response.text}"}
        plan = plan_response.json()
        plan_id = plan["id"]
        root_suite_id = plan["rootSuite"]["id"]
        # 2. Create static test suite
        suite_url = f"{organization_url}/{project_name}/_apis/testplan/Plans/{plan_id}/suites?api-version=5.0"
        suite_body = {
            "suiteType": "StaticTestSuite",
            "name": suite_name,
            "parentSuite": {"id": root_suite_id}
        }
        suite_response = requests.post(suite_url, headers=headers, json=suite_body)
        if suite_response.status_code not in (200, 201):
            return {"error": f"Error creating test suite: {suite_response.status_code} {suite_response.text}"}
        suite = suite_response.json()
        suite_id = suite["id"]
        # 3. Create test cases
        test_case_ids = []
        for tc in test_cases:
            tc_title = tc.title
            work_item_data = [
                {"op": "add", "path": "/fields/System.Title", "from": None, "value": tc_title}
            ]
            test_case_url = f"{organization_url}/{project_name}/_apis/wit/workitems/$Test%20Case?api-version=5.0"
            tc_headers = headers.copy()
            tc_headers['Content-Type'] = 'application/json-patch+json'
            tc_response = requests.post(test_case_url, headers=tc_headers, json=work_item_data)
            if tc_response.status_code in (200, 201):
                tc_json = tc_response.json()
                test_case_ids.append(tc_json["id"])
            else:
                return {"error": f"Error creating test case '{tc_title}': {tc_response.status_code} {tc_response.text}"}
        # 4. Add test cases to the suite
        if test_case_ids:
            test_case_ids_str = ','.join(str(tc_id) for tc_id in test_case_ids)
            add_case_url = f"{organization_url}/{project_name}/_apis/test/Plans/{plan_id}/suites/{suite_id}/testcases/{test_case_ids_str}?api-version=5.0"
            add_case_response = requests.post(add_case_url, headers=headers)
            if add_case_response.status_code not in (200, 201):
                return {"error": f"Error adding test cases: {add_case_response.status_code} {add_case_response.text}"}
        return {
            "plan_id": plan_id,
            "suite_id": suite_id,
            "test_case_ids": test_case_ids,
            "message": f"Test plan '{plan_name}', suite '{suite_name}', and {len(test_case_ids)} test cases created and added to the suite."
        }
    except Exception as e:
        return {"error": f"Failed to create test plan with cases: {str(e)}"}

@kernel_function()
def find_code_agent_commit(pat: str, org_url: str, project_name: str):
    """Find the latest commit in the default repository of the specified Azure DevOps project, including its branch."""
    try:
        organization_url = org_url.rstrip('/')
        auth_string = f":{pat}"
        authorization = base64.b64encode(auth_string.encode('ascii')).decode('ascii')
        headers = {
            'Content-Type': 'application/json',
            'Authorization': 'Basic ' + authorization
        }
        # 1. Get default repository for the project
        repo_url = f"{organization_url}/{project_name}/_apis/git/repositories?api-version=7.1"
        repo_response = requests.get(repo_url, headers=headers)
        if repo_response.status_code != 200:
            return {"error": f"Error fetching repositories: {repo_response.status_code} {repo_response.text}"}
        repos = repo_response.json().get('value', [])
        if not repos:
            return {"error": "No repositories found in the project."}
        default_repo = next((r for r in repos if r.get('isDefault')), repos[0])
        repo_id = default_repo['id']
        repo_name = default_repo['name']
        # 2. Get the latest commit
        commits_url = f"{organization_url}/{project_name}/_apis/git/repositories/{repo_id}/commits?$top=1&api-version=7.1"
        commits_response = requests.get(commits_url, headers=headers)
        if commits_response.status_code != 200:
            return {"error": f"Error fetching commits: {commits_response.status_code} {commits_response.text}"}
        commits = commits_response.json().get('value', [])
        if not commits:
            return {"error": "No commits found in the repository."}
        commit = commits[0]
        commit_id = commit.get('commitId')
        # 3. Get branch for the commit
        branches_url = f"{organization_url}/{project_name}/_apis/git/repositories/{repo_id}/refs?filter=heads/&api-version=7.1"
        branches_response = requests.get(branches_url, headers=headers)
        branch_name = None
        if branches_response.status_code == 200:
            branches = branches_response.json().get('value', [])
            for branch in branches:
                # Get the branch name and its objectId (commit)
                if branch.get('objectId') == commit_id:
                    # branch['name'] is in the format 'refs/heads/branchName'
                    branch_name = branch.get('name', '').replace('refs/heads/', '')
                    break
        # 4. Return commit details
        result = {
            "commit_id": commit_id,
            "author": commit.get('author', {}).get('name'),
            "date": commit.get('author', {}).get('date'),
            "comment": commit.get('comment'),
            "repo_name": repo_name,
            "branch": branch_name,
            "message": f"Latest commit in repo '{repo_name}' found." + (f" Branch: {branch_name}" if branch_name else " Branch not found.")
        }
        print(result)
        return result
    except Exception as e:
        return {"error": f"Failed to find latest commit: {str(e)}"}

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
