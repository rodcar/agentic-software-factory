import azure.functions as func
import logging
import json
import requests
import threading
import os

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

def trigger_issue_research(payload):
    try:
        requests.post(
            os.environ.get("ISSUE_RESEARCH_ENDPOINT"),
            headers={"Content-Type": "application/json"},
            data=json.dumps(payload),
            timeout=5  # Very short timeout just for connection
        )
    except Exception as e:
        logging.error(f"Failed to call issue_research endpoint: {str(e)}")

@app.route(route="az_devops_webhook")
def az_devops_webhook(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')

    try:
        req_body = req.get_json()
    except ValueError:
        return func.HttpResponse("Invalid JSON body.", status_code=400)

    resource = req_body.get("resource", {})
    fields = resource.get("fields", {})
    project_name = fields.get("System.TeamProject")
    work_item_type = fields.get("System.WorkItemType")
    bug_content = fields.get("System.Title")

    if work_item_type == "Bug":
        if '[AGENT]' not in bug_content:
            return func.HttpResponse(
                "No [AGENT] tag in the bug content.",
                status_code=200
            )

        payload = {
            "issue": bug_content,
            "project_name": project_name
        }

        # Fire and forget: call in a background thread
        threading.Thread(target=trigger_issue_research, args=(payload,)).start()

        # Immediately respond to JIRA
        return func.HttpResponse(
            json.dumps({"result": "triggered"}),
            mimetype="application/json",
            status_code=200
        )
    else:
        return func.HttpResponse(
            "Not a bug work item.",
            status_code=200
        )
