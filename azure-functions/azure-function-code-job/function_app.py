import azure.functions as func
import logging
import json
import time
import os
import uuid
from azure_container_instances_utils import create_container, wait_for_container_termination

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

# Azure Container Registry credentials
SUBSCRIPTION_ID = os.environ.get("SUBSCRIPTION_ID")
RESOURCE_GROUP = os.environ.get("RESOURCE_GROUP")
CONTAINER_IMAGE = os.environ.get("CONTAINER_IMAGE")
CONTAINER_IMAGE_CODEX = os.environ.get("CONTAINER_IMAGE_CODEX")
REGISTRY_SERVER = os.environ.get("REGISTRY_SERVER")
REGISTRY_USERNAME = os.environ.get("REGISTRY_USERNAME")
REGISTRY_PASSWORD = os.environ.get("REGISTRY_PASSWORD")

# LLM credentials
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
 
# Get Azure service principal credentials from environment variables
AZURE_TENANT_ID = os.environ.get("AZURE_TENANT_ID")
AZURE_CLIENT_ID = os.environ.get("AZURE_CLIENT_ID")
AZURE_CLIENT_SECRET = os.environ.get("AZURE_CLIENT_SECRET")

@app.route(route="code_job")
def code_job(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')

    try:
        req_body = req.get_json()
    except ValueError:
        req_body = {}

    # Extract parameters from the request body
    pat = req_body.get('pat')
    org_url = req_body.get('org_url')
    project_name = req_body.get('project_name')
    functional_spec = req_body.get('functional_spec')
    test_plan = req_body.get('test_plan')
    code_agent = req_body.get('code_agent')
    job_type = req_body.get('job_type', 'code_job')

    # Print the parameters for debugging multiline
    logging.info(f"PAT: {pat}")
    logging.info(f"Org URL: {org_url}")
    logging.info(f"Project Name: {project_name}")
    logging.info(f"Functional Spec: {functional_spec}")
    logging.info(f"Test Plan: {test_plan}")
    logging.info(f"Code Agent: {code_agent}")

    # Initialize variables to avoid UnboundLocalError
    branch_name = None
    commit_id = None

    # Wait for 10 seconds
    #time.sleep(10)

    if (job_type == "implementation"):
        try:
            # Create container instance with issue description as prompt
            container_group_name = f"claude-job-{uuid.uuid4().hex[:8]}"

            # Prompt for the code agent
            prompt = f"/project:implement functional spec: '{functional_spec}' and implement the following tests: '{test_plan}'. Important: Push code to origin."

            repository_url = f"https://{pat}@dev.azure.com/your-organization/{project_name}/_git/{project_name}"

            # Create environment variables for the container
            env_vars = {
                "REPOSITORY_URL": repository_url,
                "ANTHROPIC_API_KEY": ANTHROPIC_API_KEY,
                "PROMPT": prompt
            }

            container_result = None
            
            if 'claude' in code_agent:
                # Create the container
                container_result = create_container(
                    subscription_id=SUBSCRIPTION_ID,
                    resource_group=RESOURCE_GROUP,
                    container_group_name=container_group_name,
                    container_image=CONTAINER_IMAGE,
                    registry_server=REGISTRY_SERVER,
                    registry_username=REGISTRY_USERNAME,
                    registry_password=REGISTRY_PASSWORD,
                    environment_variables=env_vars,
                    tenant_id=AZURE_TENANT_ID,
                    client_id=AZURE_CLIENT_ID,
                    client_secret=AZURE_CLIENT_SECRET
                )
            elif 'codex' in code_agent:
                # Reassign name
                container_group_name = f"codex-job-{uuid.uuid4().hex[:8]}"
                
                # Prompt for the code agent
                # Implementation Prompt
                implementation_prompt = f"""Implement the following: {prompt}.
                Follow these steps:
                1. Understand the functional spec and tests described
                2. Create the project structure and files
                3. Implement a solution that addresses the functional spec
                4. Implement tests
                5. Prepare a concise PR title and description
                6. Create a new branch with the change and make a push to origin

                Check the following before push:
                - Exclude the `.claude` folder from the commit.
                - Decorate fixtures (e.g., `client`) with `@pytest.fixture`.
                - Decorate test functions with `@pytest.mark.testcase("test_name_here")`.
                - Place all tests inside the `tests/` folder.
                - Add a `requirements.txt` without specifying library versions (include test dependencies).
                - Default to Python, Flask, and in-memory DB unless otherwise specified.
                - Include `azure-pipelines.yml` in the commit."""
                
                # Custom env vars
                env_vars = {
                    "REPOSITORY_URL": repository_url,
                    "OPENAI_API_KEY": OPENAI_API_KEY,
                    "QUERY": implementation_prompt
                }

                # Create the container
                container_result = create_container(
                    subscription_id=SUBSCRIPTION_ID,
                    resource_group=RESOURCE_GROUP,
                    container_group_name=container_group_name,
                    container_image=CONTAINER_IMAGE_CODEX, # Replace with your Codex image
                    registry_server=REGISTRY_SERVER,
                    registry_username=REGISTRY_USERNAME,
                    registry_password=REGISTRY_PASSWORD,
                    environment_variables=env_vars,
                    tenant_id=AZURE_TENANT_ID,
                    client_id=AZURE_CLIENT_ID,
                    client_secret=AZURE_CLIENT_SECRET
                )  
            
            # Log the container creation result
            logging.info(f"Created container instance: {container_result.name}")

            # Wait for container to reach "Terminated" state
            logging.info(f"Waiting for container {container_result.name} to terminate...")
                
            # Set a reasonable timeout for an Azure Function (up to 10 minutes)
            container_final_state = wait_for_container_termination(
                subscription_id=SUBSCRIPTION_ID,
                resource_group=RESOURCE_GROUP,
                container_group_name=container_group_name,
                tenant_id=AZURE_TENANT_ID,
                client_id=AZURE_CLIENT_ID,
                client_secret=AZURE_CLIENT_SECRET,
                timeout_seconds=600,  # 10 minute timeout
                check_interval_seconds=15  # Check every 15 seconds
            )

            if container_final_state:
                # Get exit code if available
                instance_view = container_final_state.containers[0].instance_view
                exit_code = instance_view.current_state.exit_code if hasattr(instance_view.current_state, 'exit_code') else "unknown"
                
                termination_message = f"Container {container_result.name} terminated with exit code: {exit_code}"
                logging.info(termination_message)

                # Generate a branch name and commit ID based on the provided parameters
                #branch_name = "feature-container-name"  # Placeholder for branch name generation logic
                #commit_id = "a77c2o3n4tainer"  # Placeholder for commit ID generation logic

                #result = {
                #    "branch_name": branch_name,
                #    "commit_id": commit_id
                #}

                #logging.info(f"Generated branch name: {branch_name}, commit ID: {commit_id}")

                result = {
                    "message": "The code agent has implemented the project",
                }

                return func.HttpResponse(
                    json.dumps(result),
                    mimetype="application/json",
                    status_code=200
                )
            else:
                timeout_message = f"Container {container_result.name} did not terminate within the timeout period. Container job is still running."
                logging.warning(timeout_message)
                return {"result": f"container instance: {container_result.name}. {timeout_message}"}
        except Exception as e:
            logging.error(f"Error processing: {str(e)}")
            return {"error": f"Error processing: {str(e)}"}
    elif (job_type == "fix"):
        print("Fix job type selected")
        issue = req_body.get('issue')
        report = req_body.get('report')
        try:
            # Create container instance with issue description as prompt
            container_group_name = f"claude-job-{uuid.uuid4().hex[:8]}"

            # Prompt for the code agent
            prompt = f"/project:fix-issue '{issue}', Report: '{report}'. Important: Push code to origin repository."

            print(f"Prompt: {prompt}")

            repository_url = f"https://{pat}@dev.azure.com/your-organization/{project_name}/_git/{project_name}"

            # Create environment variables for the container
            env_vars = {
                "REPOSITORY_URL": repository_url,
                "ANTHROPIC_API_KEY": ANTHROPIC_API_KEY,
                "PROMPT": prompt
            }
            
            # Create the container
            container_result = create_container(
                subscription_id=SUBSCRIPTION_ID,
                resource_group=RESOURCE_GROUP,
                container_group_name=container_group_name,
                container_image=CONTAINER_IMAGE,
                registry_server=REGISTRY_SERVER,
                registry_username=REGISTRY_USERNAME,
                registry_password=REGISTRY_PASSWORD,
                environment_variables=env_vars,
                tenant_id=AZURE_TENANT_ID,
                client_id=AZURE_CLIENT_ID,
                client_secret=AZURE_CLIENT_SECRET
            )
            
            # Log the container creation result
            logging.info(f"Created container instance: {container_result.name}")

            # Wait for container to reach "Terminated" state
            logging.info(f"Waiting for container {container_result.name} to terminate...")
                
            # Set a reasonable timeout for an Azure Function (up to 10 minutes)
            container_final_state = wait_for_container_termination(
                subscription_id=SUBSCRIPTION_ID,
                resource_group=RESOURCE_GROUP,
                container_group_name=container_group_name,
                tenant_id=AZURE_TENANT_ID,
                client_id=AZURE_CLIENT_ID,
                client_secret=AZURE_CLIENT_SECRET,
                timeout_seconds=600,  # 10 minute timeout
                check_interval_seconds=15  # Check every 15 seconds
            )

            if container_final_state:
                # Get exit code if available
                instance_view = container_final_state.containers[0].instance_view
                exit_code = instance_view.current_state.exit_code if hasattr(instance_view.current_state, 'exit_code') else "unknown"
                
                termination_message = f"Container {container_result.name} terminated with exit code: {exit_code}"
                logging.info(termination_message)

                # Generate a branch name and commit ID based on the provided parameters
                #branch_name = "feature-container-name"  # Placeholder for branch name generation logic
                #commit_id = "a77c2o3n4tainer"  # Placeholder for commit ID generation logic

                #result = {
                #    "branch_name": branch_name,
                #    "commit_id": commit_id
                #}

                #logging.info(f"Generated branch name: {branch_name}, commit ID: {commit_id}")

                result = {
                    "message": "The code agent has fixed the issue",
                }

                return func.HttpResponse(
                    json.dumps(result),
                    mimetype="application/json",
                    status_code=200
                )
            else:
                timeout_message = f"Container {container_result.name} did not terminate within the timeout period. Container job is still running."
                logging.warning(timeout_message)
                return {"result": f"container instance: {container_result.name}. {timeout_message}"}
        except Exception as e:
            logging.error(f"Error processing: {str(e)}")
            return {"error": f"Error processing: {str(e)}"}

    # Only return result if branch_name and commit_id are set
    if branch_name is not None and commit_id is not None:
        result = {
            "branch_name": branch_name,
            "commit_id": commit_id
        }
        return func.HttpResponse(
            json.dumps(result),
            mimetype="application/json",
            status_code=200
        )
    else:
        # Return an error if no job was processed
        return func.HttpResponse(
            json.dumps({"error": "No job was processed or job_type not supported."}),
            mimetype="application/json",
            status_code=400
        )