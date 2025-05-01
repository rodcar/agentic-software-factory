import asyncio
import os
from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.teams import MagenticOneGroupChat
from autogen_agentchat.conditions import MaxMessageTermination
from foundry_assistant_agent import FoundryAssistantAgent

def run_issue_research(creds: dict, issue: str) -> str:
    """
    Runs the agent team on an issue description and returns the content of the last message (report).
    Uses the creds dict for all credentials instead of os.getenv.
    """
    async def _run():
        model_client = OpenAIChatCompletionClient(
            model="gpt-4o",
            api_key=creds.get("OPENAI_API_KEY")
        )

        objective = f"The following is a issue: <issue>{issue}</issue>. Your task is the following: 1. Propose an initial fix for this issue. 2. IssueTrackerAgent: Always try to get information on past issues and fixes. 3. Search on Bing for a potential fix for the issue, look into the pages to potential code fixes, look for multiple options. 4. Update your proposed fix based on the new information if relevant. 5. Evaluate if the information is good enough to continue to the report, otherwise continue with the search on the web and in the issue tracker. 5. Create a short markdown report of the issue and proposed fix."

        fix_proposer_agent = AssistantAgent(
            name="FixProposer",
            model_client=model_client,
            system_message="""You are a FixProposer Agent. You receive an issue description. Propose a fix for the issue. Return: 'Proposed fix: <code>'"""
        )

        issue_tracker_agent = FoundryAssistantAgent(
            name="IssueTrackerAgent",
            agent_id=creds.get("INTERNET_AGENT_ID_ISSUE_TRACKER"),
            conn_str=creds.get("INTERNET_AGENT_CONN_STR"),
            description="""You are an IssueTrackerAgent. You receive an issue description. You return information about similar past issues and fixes."""
        )

        bing_search_agent = FoundryAssistantAgent(
            name="InternetSearchAgent",
            agent_id=creds.get("INTERNET_AGENT_ID_BING_SEARCH"),
            conn_str=creds.get("INTERNET_AGENT_CONN_STR"),
            description="You are an InternetSearchAgent using Bing Search. Search for potential fixes for the given issue and return relevant code snippets and explanations using Bing Search."
        )

        report_generator = AssistantAgent(
            name="ReportGenerator",
            model_client=model_client,
            system_message="""You are a ReportGenerator Agent. You write reports. Do not add extra comments."""
        )

        termination_condition = MaxMessageTermination(max_messages=20)

        team = MagenticOneGroupChat(
            participants=[fix_proposer_agent, issue_tracker_agent, bing_search_agent, report_generator],
            model_client=model_client,
            termination_condition=termination_condition,
            emit_team_events=True
        )

        result = await team.run(task=objective)
        if result.messages:
            last_msg = result.messages[-1]
            content = str(last_msg.content)
            return content

    return asyncio.run(_run())
