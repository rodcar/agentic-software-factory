import azure.functions as func
import logging
import os
import json
import requests

import issue_research_runner

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

@app.route(route="issue_research")
def issue_research(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')

    issue = None
    project_name = None
    if not req.headers.get('content-type', '').startswith('application/json'):
        return func.HttpResponse(
            'Content-Type must be application/json.',
            status_code=400
        )
    try:
        req_body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            'Invalid or missing JSON body.',
            status_code=400
        )
    issue = req_body.get('issue')
    project_name = req_body.get('project_name')
    if not issue or not project_name:
        return func.HttpResponse(
            'Both "issue" and "project_name" must be provided in the JSON body.',
            status_code=400
        )
    # You can now use 'issue' and 'project_name' variables as needed

    logging.info(f"Received issue: {issue}")
    logging.info(f"Received project_name: {project_name}")

    creds = {
        "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY"),
        "INTERNET_AGENT_ID_ISSUE_TRACKER": os.environ.get("INTERNET_AGENT_ID_ISSUE_TRACKER"),
        "INTERNET_AGENT_CONN_STR": os.environ.get("INTERNET_AGENT_CONN_STR"),
        "INTERNET_AGENT_ID_BING_SEARCH": os.environ.get("INTERNET_AGENT_ID_BING_SEARCH"),
    }
    # Ensure these keys are present in local.settings.json under "Values"

    # Print credentials for debugging (remove in production)
    for key, value in creds.items():
        if value is None:
            logging.warning(f"{key} is not set.")
        else:
            logging.info(f"{key} is set.")

    logging.info("Running issue research...")
    researcher_result = issue_research_runner.run_issue_research(creds, issue)

    logging.info("Issue research completed.")
    logging.info(f"Researcher result: {researcher_result}")
    code_job_url = os.environ.get("CODE_JOB_URL")

    logging.info(f"Code job URL: {code_job_url}")

    code_job_payload = {
        "pat": os.environ.get("AZURE_DEVOPS_PAT"),
        "org_url": os.environ.get("AZURE_DEVOPS_ORG_URL"),
        "project_name": project_name,
        "issue": issue,
        "report": researcher_result,
        "code_agent": "claude-code",
        "job_type": "fix"
    }

    response = requests.post(
        code_job_url,
        json=code_job_payload,
        timeout=1200
    )

    logging.info(f"Code job response: {response.status_code}")

    result = {
        "status_code": response.status_code,
        "report": researcher_result
    }

    return func.HttpResponse(
        json.dumps(result),
        status_code=200,
        mimetype="application/json"
    )