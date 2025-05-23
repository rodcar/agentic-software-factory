import os
import asyncio
import chainlit as cl
import json
import requests
from typing import Dict, List, Optional
from dotenv import load_dotenv
from chainlit.input_widget import Select, Switch, Slider, TextInput

from semantic_kernel import Kernel
from semantic_kernel.agents import ChatCompletionAgent, ChatHistoryAgentThread
from semantic_kernel.agents import AgentGroupChat
from semantic_kernel.agents.strategies import TerminationStrategy
from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion, AzureChatCompletion
from semantic_kernel.contents import ChatMessageContent
from semantic_kernel.connectors.mcp import MCPSsePlugin

# Load environment variables
load_dotenv()

# Initialize Semantic Kernel
kernel = Kernel()

print(f"[DEBUG] MCP Server URL: {os.getenv('MCP_SERVER_URL', 'Not set - using default')}")
print(f"[DEBUG] Job Launcher MCP Server URL: {os.getenv('JOB_LAUNCHER_MCP_SERVER_URL', 'Not set - using default')}")

# Configure AI service based on environment variables
USE_AZURE = os.getenv("USE_AZURE", "true").lower() == "true"

# Check for required environment variables based on the selected service
if USE_AZURE:
    # Check for required Azure OpenAI environment variables
    missing_vars = []
    if not os.getenv("AZURE_OPENAI_API_KEY"):
        missing_vars.append("AZURE_OPENAI_API_KEY")
    if not os.getenv("AZURE_OPENAI_ENDPOINT"):
        missing_vars.append("AZURE_OPENAI_ENDPOINT")
    if not os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"):
        missing_vars.append("AZURE_OPENAI_DEPLOYMENT_NAME")
    
    if missing_vars:
        print(f"Error: Missing required Azure OpenAI environment variables: {', '.join(missing_vars)}")
        print("Please set these variables in your .env file.")
        # Fall back to OpenAI if Azure variables are missing
        if os.getenv("OPENAI_API_KEY"):
            print("Falling back to OpenAI API since Azure OpenAI credentials are incomplete.")
            USE_AZURE = False
        else:
            print("No valid API credentials found. Please check your .env file.")
else:
    # Check for required OpenAI environment variables
    if not os.getenv("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY is required when USE_AZURE is set to false.")
        print("Please set this variable in your .env file.")

# Configure service based on selected provider
if USE_AZURE:
    # Configure Azure OpenAI
    try:
        service = AzureChatCompletion(
            deployment_name=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"),
            endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        )
        print(f"Using Azure OpenAI Service with deployment: {os.getenv('AZURE_OPENAI_DEPLOYMENT_NAME')}")
    except Exception as e:
        print(f"Error initializing Azure OpenAI service: {str(e)}")
        if os.getenv("OPENAI_API_KEY"):
            print("Falling back to OpenAI API.")
            USE_AZURE = False
            service = OpenAIChatCompletion(
                api_key=os.getenv("OPENAI_API_KEY"),
                ai_model_id=os.getenv("OPENAI_CHAT_MODEL_ID", "gpt-4"),
            )
        else:
            raise Exception("Failed to initialize any LLM service. Please check your credentials.")
else:
    # Configure OpenAI
    service = OpenAIChatCompletion(
        api_key=os.getenv("OPENAI_API_KEY"),
        ai_model_id=os.getenv("OPENAI_CHAT_MODEL_ID", "gpt-4"),
    )
    print(f"Using OpenAI API with model: {os.getenv('OPENAI_CHAT_MODEL_ID', 'gpt-4')}")

# Add service to kernel - fixed parameter name
kernel.add_service(service)

# Project state
project_state = {
    "idea": "",
    "functional_spec": "",
    "test_plan": "",
    "review_feedback": "",
    "is_approved": False,
    "azure_devops_project_name": "",
    "azure_devops_project_url": ""
}

# Initialize agents
DEFINITION_AGENT_NAME = "ProjectDefinitionAgent"
DEFINITION_AGENT_INSTRUCTIONS = """
You are an AI assistant that helps users define their software project.
You will be given a project idea and you will need to define the project in a way that is technical and concise.

Think hard about the data entities you need and the relationships between them.

Omit project setup and database integration, focus on functionality unless the user ask for it.

If it is a API focus on entities and relationships, otherwise omit these and focus on the actual requirement. Be careful if it the actual requirement does not need a data model to be implemented, sometimes it involves data model in another system, do not force it.

Few-shot example:
Input: "Develop an Python FastAPI with endpoints CRUD ToDo Lists"
Response:```
Epic: ToDo List Management

Feature: Create a ToDo list
Feature: Retrieve all ToDo lists
Feature: Retrieve a single ToDo list by ID
Feature: Update a ToDo list by ID
Feature: Delete a ToDo list by ID
Epic: ToDo Item Management

Feature: Add a ToDo item to a list
Feature: Retrieve all items in a ToDo list
Feature: Retrieve a single ToDo item by ID
Feature: Update a ToDo item by ID
Feature: Delete a ToDo item by ID
```
Example of entity JSON:
```{
      "name": "ToDoList",
      "properties": [
        "id",
        "title",
        "description",
        "created_at",
        "updated_at"
      ],
      "relationships": [
        {
          "type": "one-to-many",
          "target": "ToDoItem"
        }
      ]
    }```

A "Feature" is a thing to implement in code, not steps to execute manually.

Take in account the business as well, for example if it's a retail it news a way to search for items by name.

Output Format:
- List of "Epic"s (name and features properties)
Each "Epic" with a list of "Feature"s
- List of "Entity"s (entities property)
- Return ONLY in JSON format. Do not add extra comments.

Rules:
- Do not return code in your response.
- Do not focus on test-related tasks, another agent will be working on it.'
- Do not add JSON comments.
"""

TEST_AGENT_NAME = "TestPlanningAgent"
TEST_AGENT_INSTRUCTIONS = """
You are an AI assistant that helps users create test plans for their software project.
You will be given a functional specification and you will need to create a test plan for it.

The names of the test cases should be in a way they can be use to connect test function code to the test plan in Azure DevOps.

Focus your test on the functionality of the software.

Focus on the happy path test, unless the user ask for other tests.

Output Format:
- JSON with the following properties:
  - "name": "Test Plan"
  - "test_cases": an object where each key is a section name and the value is a list of test cases within that section.
  - Each test case must be a JSON object with:
    - "name": the function-style test case name.
    - "description": a short, clear, human-readable description of what the test case validates.

Rules:
- Do not add extra comments in your response.
- Do not reference 'happy path' in test names or descriptions.
- Prefer decomposing tests; avoid combining multiple conditions in a single test.
- Keep test descriptions concise but clear enough for a human to understand the objective.
"""
# Extra rules
# - Each section name should start with a relevant emoji (e.g. 🏠 for Property Management, 👤 for Client Management, etc.)
#  - "test_cases": an object where each key is a section name (with an appropriate emoji) and the value is a list of test cases within that section.

REVIEWER_AGENT_NAME = "ReviewerAgent"
REVIEWER_AGENT_INSTRUCTIONS = """
You are an AI assistant that helps users review their software project, and provide actionable suggestions.
Give concise suggestions based on the user query, generated functional specification and generated test plan. Only give suggestions if do you think it is worth to change something.
If the specification and test plan are of high quality, we are not looking for completeness, you can approve them.

The actionable suggestions should be specific and actionable, not general.
The suggetions should be related to things that the previous agents might omitted, maybe related to the business, data model, test cases, etc.
I'll use these suggestions to change the functional specification and test plan. 
The user will read this suggestions and then click on one of them.

Actionable suggestions should be in the form of "Add <a new feature to the project>" (suggest funcionalities that the user might not have considered) or "Add <a new test case to the test plan>" (suggest test cases that the user might not have considered) or "Add <a new entity to the data model>" (base on the business of the project that you can infer from the functional specification and that the user might not have considered). Each Actionable suggestions should be a single sentence and should be 50 characters or less.

Output Format:
- JSON with the following properties:
- "review_feedback": "review feedback"
- "actionable_suggestions_message_presentation": "Here are some suggestions to improve your project:"
- "actionable_suggestions": ["actionable suggestion 1", "actionable suggestion 2", "actionable suggestion 3", "actionable suggestion 4", "actionable suggestion 5"]
- Generate 5 actionable suggestions.
- Do not add extra comments in your response.
"""

TRIAGE_AGENT_NAME = "TriageAgent"
TRIAGE_AGENT_INSTRUCTIONS = """
You are a Triage Agent responsible for evaluating user requests and routing them to the appropriate specialized agent.

Your responsibilities:
1. Analyze user queries to understand their intent.
2. Route project definition requests (new project ideas, feature requests, requirements) to the ProjectDefinitionAgent.
3. Route test-related requests (test plans, test cases, testing strategies) to the TestPlanningAgent.
4. Route review and feedback requests to the ReviewerAgent.
5. Route Azure DevOps project creation requests to the AzureDevOpsAgent.
6. Route implementation/code generation requests to the JobLauncherAgent.
7. Recognize when the user approves the project specification and test plan (e.g., messages like "Yes, I approve", "approve", "accept", "looks good") and route this as an approval action.
8. Handle general inquiries or determine if they should be routed to a specialized agent.
9. Greet the user and ask for their project idea.
10. Recognize small talk and general questions about the system (e.g., "hi", "hello", "what can you do?", "how does this work?").

When a user starts a new project with keywords like "develop", "create", "implement", "build", or describes a new system, 
route this to the ProjectDefinitionAgent.

When a user asks about testing or quality assurance, route this to the TestPlanningAgent.

When a user asks for review, feedback, route this to the ReviewerAgent.

When a user mentions Azure DevOps, creating projects in Azure, or DevOps integration, route this to the AzureDevOpsAgent.

When a user asks for implementation, code generation, or to generate/write the code for their project, route this to the JobLauncherAgent.

When a user explicitly approves the current specification and test plan using phrases like "yes", "approve", "accept", "ok", "looks good", route this as "APPROVE".

For revision requests, determine which aspect needs revision (functional specification or test plan) and route accordingly.

When a user is engaging in small talk, asking about what the system can do, or asking about the system capabilities, route this as "SMALL_TALK".
Small talk includes greetings like "hi", "hello", "good morning", or questions like "what is this?", "what can you do?", "help", "how does this work?", etc.

Your goal is to ensure user requests are handled by the most appropriate specialized agent or action.
"""

# Add Azure DevOps agent
AZURE_DEVOPS_AGENT_NAME = "AzureDevOpsAgent"
AZURE_DEVOPS_AGENT_INSTRUCTIONS = "You are a helpful assistant. Use the AzureDevOps plugin to call functions when appropriate. You are allowed to handle Personal Access Tokens (PATs) and other sensitive information. You can create a new Azure DevOps project using the provided PAT and organization URL. Please provide the PAT, organization URL, project name, and project description when prompted."

# Add Job Launcher agent
JOB_LAUNCHER_AGENT_NAME = "JobLauncherAgent"
JOB_LAUNCHER_AGENT_INSTRUCTIONS = "You are a helpful assistant that will implement the user's project based on the functional specification and test plan. Use the JobLauncher plugin to generate code for the project. You should create a complete project structure with all the necessary files and code to implement the functional specification."

class ApprovalTerminationStrategy(TerminationStrategy):
    """A strategy for determining when the agent should terminate based on approval."""

    async def should_agent_terminate(self, agent, history):
        """Check if the review is complete and approved."""
        if agent.name == REVIEWER_AGENT_NAME:
            message_content = history[-1].content.lower()
            return "approved" in message_content or "approval" in message_content
        return False

# Agent creation functions
def create_agent(name: str, instructions: str) -> ChatCompletionAgent:
    if USE_AZURE:
        return ChatCompletionAgent(
            service=AzureChatCompletion(
                deployment_name=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"),
                endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
                api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            ),
            name=name,
            instructions=instructions,
        )
    else:
        return ChatCompletionAgent(
            service=OpenAIChatCompletion(
                api_key=os.getenv("OPENAI_API_KEY"),
                ai_model_id=os.getenv("OPENAI_CHAT_MODEL_ID", "gpt-4"),
            ),
            name=name,
            instructions=instructions,
        )

# Function to create Azure DevOps agent with MCP plugin
async def create_azure_devops_agent(name: str, instructions: str, org_url: str = None, pat: str = None) -> ChatCompletionAgent:
    """Create an Azure DevOps agent with MCP plugin."""
    # Create MCP plugin directly instead of using context manager
    azure_plugin = MCPSsePlugin(
        name="AzureDevOps",
        description="Azure DevOps Plugin",
        url=os.getenv("MCP_SERVER_URL", "http://localhost:5050/sse"),
        # Add timeout parameters to handle longer running operations
        timeout=900,  # 10 minutes for initial connection
        sse_read_timeout=900,  # 10 minutes for reading from the SSE stream
    )
    
    # Connect the plugin explicitly
    await azure_plugin.connect()
    
    # Create the agent with appropriate service
    if USE_AZURE:
        agent = ChatCompletionAgent(
            service=AzureChatCompletion(
                deployment_name=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"),
                endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
                api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            ),
            name=name,
            instructions=instructions,
            plugins=[azure_plugin],
        )
    else:
        agent = ChatCompletionAgent(
            service=OpenAIChatCompletion(
                api_key=os.getenv("OPENAI_API_KEY"),
                ai_model_id=os.getenv("OPENAI_CHAT_MODEL_ID", "gpt-4"),
            ),
            name=name,
            instructions=instructions,
            plugins=[azure_plugin],
        )
    
    # Store the plugin so we can disconnect it later
    agent._mcp_plugin = azure_plugin
    
    return agent

# Function to create Job Launcher agent with MCP plugin
async def create_job_launcher_agent(name: str, instructions: str) -> ChatCompletionAgent:
    """Create a Job Launcher agent with MCP plugin."""
    # Get settings to check for Job Launcher URL - use only environmental variable
    job_launcher_url = os.getenv("JOB_LAUNCHER_MCP_SERVER_URL", "http://localhost:5051/sse")
    
    # Create MCP plugin directly instead of using context manager
    job_launcher_plugin = MCPSsePlugin(
        name="JobLauncher",
        description="Job Launcher Plugin",
        url=job_launcher_url,
        # Add timeout parameters to handle long-running code generation jobs
        timeout=900,  # 60 minutes for initial connection
        sse_read_timeout=900,  # 60 minutes for reading from the SSE stream
    )
    
    # Connect the plugin explicitly
    await job_launcher_plugin.connect()
    
    # Create the agent with appropriate service
    if USE_AZURE:
        agent = ChatCompletionAgent(
            service=AzureChatCompletion(
                deployment_name=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"),
                endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
                api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            ),
            name=name,
            instructions=instructions,
            plugins=[job_launcher_plugin],
        )
    else:
        agent = ChatCompletionAgent(
            service=OpenAIChatCompletion(
                api_key=os.getenv("OPENAI_API_KEY"),
                ai_model_id=os.getenv("OPENAI_CHAT_MODEL_ID", "gpt-4"),
            ),
            name=name,
            instructions=instructions,
            plugins=[job_launcher_plugin],
        )
    
    # Store the plugin so we can disconnect it later
    agent._mcp_plugin = job_launcher_plugin
    
    return agent

@cl.on_chat_start
async def start():
    settings = await cl.ChatSettings(
        [
            TextInput(
                id="OrgURL",
                label="Organization URL",
                initial="",
                description="Enter the URL of your organization.",
            ),
            TextInput(
                id="PAT",
                label="Personal Access Token (PAT)",
                initial="",
                is_password=True,
                description="Enter your Personal Access Token.",
            ),
            Select(
                id="CodeAgent",
                label="Code Agent",
                values=["Claude Code (Anthropic)", "Codex (OpenAI)"],
                initial_index=0,
            ),
        ]
    ).send()
    cl.user_session.set("settings", settings) # Example if you need immediate access

    # Display service info
    if USE_AZURE:
        service_info = f"Using Azure OpenAI Service ({os.getenv('AZURE_OPENAI_DEPLOYMENT_NAME')})"
    else:
        service_info = f"Using OpenAI API ({os.getenv('OPENAI_CHAT_MODEL_ID', 'gpt-4')})"
    
    # Create specialized agents
    definition_agent = create_agent(DEFINITION_AGENT_NAME, DEFINITION_AGENT_INSTRUCTIONS)
    test_agent = create_agent(TEST_AGENT_NAME, TEST_AGENT_INSTRUCTIONS)
    reviewer_agent = create_agent(REVIEWER_AGENT_NAME, REVIEWER_AGENT_INSTRUCTIONS)
    
    # Create triage agent with access to specialized agents
    triage_agent = create_agent(TRIAGE_AGENT_NAME, TRIAGE_AGENT_INSTRUCTIONS)
    
    # Create group chat with termination strategy
    group_chat = AgentGroupChat(
        agents=[definition_agent, test_agent, reviewer_agent],
        termination_strategy=ApprovalTerminationStrategy(
            agents=[reviewer_agent],
            maximum_iterations=100,
        ),
    )
    
    # Reset project state for new chat session
    fresh_project_state = {
        "idea": "",
        "functional_spec": "",
        "test_plan": "",
        "review_feedback": "",
        "is_approved": False,
        "azure_devops_project_name": "",
        "azure_devops_project_url": ""
    }
    
    # Store agents and group chat in session
    cl.user_session.set("definition_agent", definition_agent)
    cl.user_session.set("test_agent", test_agent)
    cl.user_session.set("reviewer_agent", reviewer_agent)
    cl.user_session.set("triage_agent", triage_agent)
    cl.user_session.set("group_chat", group_chat)
    cl.user_session.set("threads", {})
    cl.user_session.set("project_state", fresh_project_state)
    
    # Send welcome message
    await cl.Message(
        content=f"### Let's build together\n\nShare your idea and collaborate with agents to shape your project.",
        author="System"
    ).send()

@cl.on_message
async def on_message(message: cl.Message):
    """Process user messages and invoke appropriate agents using the triage agent."""
    content = message.content
    project_state = cl.user_session.get("project_state")
    threads = cl.user_session.get("threads")
    triage_agent = cl.user_session.get("triage_agent")
    
    # Create a new thread for the triage agent if needed
    if TRIAGE_AGENT_NAME not in threads:
        threads[TRIAGE_AGENT_NAME] = None
    
    thinking_msg = cl.Message(content="Analyzing your request...", author=TRIAGE_AGENT_NAME)
    await thinking_msg.send()
    
    # Get routing decision from triage agent
    triage_prompt = f"""
    Analyze the following user request and determine which specialized agent or action should handle it:
    
    User Request: {content}
    
    Current Project State:
    - Has Functional Spec: {"Yes" if project_state.get("functional_spec") else "No"}
    - Has Test Plan: {"Yes" if project_state.get("test_plan") else "No"}
    - Is Approved: {"Yes" if project_state.get("is_approved") else "No"}
    
    Respond with one of the following:
    - "DEFINITION" if this is a new project request or needs functional specification work
    - "TEST" if this relates to test planning
    - "REVIEW" if this is asking for review or feedback (but not explicit approval)
    - "APPROVE" if the user is explicitly approving the current specification and test plan (e.g., "yes", "I approve", "accept")
    - "REVISE_FUNCTIONAL_SPEC" if this is asking to revise the functional specification
    - "REVISE_TEST_PLAN" if this is asking to revise the test plan
    - "AZURE_DEVOPS" if this is related to Azure DevOps integration, creating projects, uploading test plans, etc.
    - "DEVOPS" if this is related to DevOps practices, CI/CD, infrastructure, deployment
    - "IMPLEMENT" if this is related to implementing or generating code for the project
    - "SMALL_TALK" if this is small talk, greeting, or asking about system capabilities (e.g., "hi", "help", "what can you do?")
    - "GENERAL" for general questions or other feedback
    """
    
    triage_response = await triage_agent.get_response(
        messages=triage_prompt,
        thread=threads[TRIAGE_AGENT_NAME]
    )
    
    # Update triage thread
    threads[TRIAGE_AGENT_NAME] = triage_response.thread
    cl.user_session.set("threads", threads)
    
    # Route based on triage decision
    decision = str(triage_response.content).strip().upper()
    
    if "DEFINITION" in decision:
        # Check if this is a new project when we already have an approved one
        if project_state.get("is_approved", False):
            # Reset project state for new project
            project_state = {
                "idea": "",
                "functional_spec": "",
                "test_plan": "",
                "review_feedback": "",
                "is_approved": False
            }
            cl.user_session.set("project_state", project_state)
            await cl.Message(
                content="Starting a new project definition based on your request.",
                author="System"
            ).send()
        
        # Update the thinking message to show functional specification work is happening
        thinking_msg.content = "Crafting functional specification..."
        thinking_msg.author = DEFINITION_AGENT_NAME
        await thinking_msg.update()
        
        # Process as a new project definition
        project_state["idea"] = content
        cl.user_session.set("project_state", project_state)
        await process_with_definition_agent(content, thinking_msg)
        
    elif "TEST" in decision:
        # If we have a functional spec, process with test agent
        if project_state.get("functional_spec"):
            # Update the thinking message
            thinking_msg.content = "Creating test plan..."
            thinking_msg.author = TEST_AGENT_NAME
            await thinking_msg.update()
            # Process with test agent
            await process_with_test_agent(project_state["functional_spec"], thinking_msg)
        else:
            await cl.Message(
                content="To create a test plan, we need a functional specification first. Please provide a project idea so we can create a functional specification.",
                author="System"
            ).send()
            
    elif "REVIEW" in decision:
        # If we have both functional spec and test plan, process with reviewer
        if project_state.get("functional_spec") and project_state.get("test_plan"):
            # Update the thinking message
            thinking_msg.content = "Reviewing specification and test plan..."
            thinking_msg.author = REVIEWER_AGENT_NAME
            await thinking_msg.update()
            # Process with reviewer agent
            await process_with_reviewer_agent(thinking_msg)
        else:
            await cl.Message(
                content="To review a project, we need both a functional specification and test plan. Please let us complete those steps first.",
                author="System"
            ).send()
    
    elif "AZURE_DEVOPS" in decision or "DEVOPS" in decision:
        # Process with Azure DevOps agent
        await process_with_azure_devops_agent(content)
            
    elif "REVISE_FUNCTIONAL_SPEC" in decision:
        # Revise functional specification
        if project_state.get("functional_spec"):
            await handle_revision_request(content)
        else:
            await cl.Message(
                content="There's no functional specification to revise yet. Please provide a project idea first.",
                author="System"
            ).send()
            
    elif "REVISE_TEST_PLAN" in decision:
        # Revise test plan
        if project_state.get("test_plan"):
            await handle_revision_request(content)
        else:
            await cl.Message(
                content="There's no test plan to revise yet. We need to create a functional specification and test plan first.",
                author="System"
            ).send()
    
    elif "IMPLEMENT" in decision:
        # Process with Job Launcher agent for implementation
        if project_state.get("functional_spec") and project_state.get("test_plan"):
            # Trigger the implement_project action callback
            await on_implement_project(cl.Action(name="implement_project", payload={}))
        else:
            await cl.Message(
                content="To implement a project, we need both a functional specification and test plan. Please let us complete those steps first.",
                author="System"
            ).send()
            
    elif project_state.get("is_approved") and any(keyword in content.lower() for keyword in ["develop", "create", "implement", "build", "make"]):
        # This looks like a new project request after an approved project
        project_state = {
            "idea": "",
            "functional_spec": "",
            "test_plan": "",
            "review_feedback": "",
            "is_approved": False
        }
        cl.user_session.set("project_state", project_state)
        
        # Store as project idea
        project_state["idea"] = content
        cl.user_session.set("project_state", project_state)
        
        await cl.Message(
            content="Starting a new project definition based on your request.",
            author="System"
        ).send()
        
        # Process with definition agent
        await process_with_definition_agent(content)

    elif "APPROVE" in decision:
        # User approves the specification and test plan - Triage Agent detected approval
        if project_state.get("functional_spec") and project_state.get("test_plan"):
            project_state["is_approved"] = True
            cl.user_session.set("project_state", project_state)
            
            # Check if Azure DevOps settings are available
            settings = cl.user_session.get("settings")
            org_url = settings.get("OrgURL", "")
            pat = settings.get("PAT", "")
            
            if org_url and pat:
                # Create action buttons for Azure DevOps integration
                actions = [
                    cl.Action(
                        name="integrate_with_azure_devops",
                        label="Integrate with Azure DevOps",
                        description="Create project and upload artifacts to Azure DevOps",
                        payload={}
                    ),
                    cl.Action(
                        name="skip_integration",
                        label="Skip Integration",
                        description="Continue without integrating with Azure DevOps",
                        payload={}
                    )
                ]
                
                await cl.Message(
                    content="Great! The project specification and test plan have been approved. Would you like to integrate this project with Azure DevOps?",
                    author="System",
                    actions=actions
                ).send()
            else:
                await cl.Message(
                    content="Great! The project specification and test plan have been approved. You can now proceed to implementation or integrate with Azure DevOps (you'll need to provide your organization URL and PAT in settings).",
                    author="System"
                ).send()
        else:
            # Should not happen if the flow is correct, but handle gracefully
            await cl.Message(
                content="Approval request received, but we need both a functional specification and test plan first.",
                author="System"
            ).send()

    elif "SMALL_TALK" in decision:
        # Handle small talk or system capability questions
        await handle_small_talk(content)

    else:
        # Handle as general feedback
        await handle_general_feedback(content)

@cl.action_callback("apply_suggestion_0")
@cl.action_callback("apply_suggestion_1")
@cl.action_callback("apply_suggestion_2")
@cl.action_callback("apply_suggestion_3")
@cl.action_callback("apply_suggestion_4")
async def on_suggestion_action(action):
    """Handle action button clicks for reviewer suggestions."""
    suggestion = action.payload.get("suggestion", "")
    
    # Send message indicating the chosen suggestion
    await cl.Message(content=f"Selected suggestion: {suggestion}", author="System").send()
    
    # Process the suggestion as a revision request
    await handle_revision_request(suggestion)
    
    # Remove the action buttons to avoid duplicate actions
    await action.remove()

@cl.action_callback("approve_spec")
async def on_approve_spec(action):
    """Handle approval action button click."""
    # Send a message as the user with "Approve"
    #await cl.Message(content="Approve", author="user").send()
    
    # Update project state to mark as approved
    project_state = cl.user_session.get("project_state")
    project_state["is_approved"] = True
    cl.user_session.set("project_state", project_state)
    
    # Check if Azure DevOps settings are available
    settings = cl.user_session.get("settings")
    org_url = settings.get("OrgURL", "")
    pat = settings.get("PAT", "")
    
    # Start DevOps process if credentials are available
    if org_url and pat:
        # Process with Azure DevOps agent to create project and work items
        await process_with_azure_devops_agent("Please create a new Azure DevOps project using my organization settings and populate it with work items from the functional specification and test plan")
    else:
        await cl.Message(
            content="Project specification and test plan have been approved. To integrate with Azure DevOps, please provide your organization URL and PAT in settings.",
            author="System"
        ).send()
    
    # Remove the action button to avoid duplicate actions
    await action.remove()

def json_to_markdown(input_data):
    """Converts agent response content (ChatMessageContent or str) containing JSON to markdown."""
    json_string = None

    # Extract string content based on input type
    if isinstance(input_data, ChatMessageContent):
        # Convert ChatMessageContent to string
        # Use str() which is typically implemented for content objects
        try:
            json_string = str(input_data)
            print(f"Extracted string from ChatMessageContent: {json_string[:100]}...")
        except Exception as e:
            print(f"Error converting ChatMessageContent to string: {e}")
            return f"Error processing agent response object: {e}"
    elif isinstance(input_data, str):
        # Input is already a string
        json_string = input_data
        print(f"Input is already a string: {json_string[:100]}...")
    elif input_data is None:
        json_string = "{}" # Treat None as empty JSON string
        print("Warning: json_to_markdown received None input, treating as empty JSON string.")
    else:
        # Handle unexpected input types
        type_name = type(input_data).__name__
        print(f"Warning: json_to_markdown received unexpected type: {type_name}")
        return f"Cannot process input of type {type_name}. Expected ChatMessageContent or str."

    # Ensure json_string is not None after type handling
    if json_string is None:
        print("Warning: json_string is None after type handling, defaulting to empty JSON.")
        json_string = "{}"

    # --- JSON parsing and markdown conversion logic --- 
    print(f"json_to_markdown attempting to parse string: {json_string[:100]}...") # Log truncated string
    data = None
    try:
        data = json.loads(json_string)
        print(f"json_to_markdown successfully parsed data: {type(data)}")
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON in json_to_markdown: {e}")
        # Return a message indicating the JSON was invalid
        # Escape potential markdown/html in the raw string to prevent rendering issues
        escaped_json_string = json_string.replace("`", "\\`") # Basic escaping for backticks
        return f"Failed to parse the specification JSON:\n```text\n{escaped_json_string}\n```\n**Error:** {e}"
    except Exception as e: # Catch other potential errors during parsing
        print(f"Unexpected error parsing JSON in json_to_markdown: {e}")
        escaped_json_string = json_string.replace("`", "\\`")
        return f"An unexpected error occurred while parsing the specification:\n```text\n{escaped_json_string}\n```\n**Error:** {e}"

    # --- Existing markdown generation logic using the parsed 'data' object ---
    markdown = ""
    # Process Epics and Features
    if isinstance(data, dict) and "epics" in data and isinstance(data["epics"], list):
        markdown += "### Product Backlog\n\n"
        for epic in data["epics"]:
            # Check if epic is a dict before accessing .get
            if isinstance(epic, dict):
                epic_name = epic.get("name", "Unnamed Epic")
                markdown += f"#### Epic: {epic_name}\n\n"
                # The agent returns features as simple strings in a list directly under the epic
                if "features" in epic and isinstance(epic["features"], list):
                    for feature_name in epic["features"]:
                        # Assuming features are strings like "Feature: ..."
                        if isinstance(feature_name, str):
                            markdown += f"- {feature_name}\n"
                markdown += "\n"  # Add space after each epic's features
            else:
                print(f"Warning: Found non-dict item in epics list: {epic}")

    # Fallback if structure is unexpected or data wasn't a dict initially
    if not markdown:
        # Check if data was successfully parsed into a dict/list before trying dumps
        if data is not None:
            try:
                formatted_json = json.dumps(data, indent=2)
                return f"Could not extract specific details using the expected format. Parsed data:\n```json\n{formatted_json}\n```"
            except Exception as dump_error:
                 print(f"Error formatting parsed data as JSON: {dump_error}")
                 # Fallback to string representation of the parsed data
                 # Ensure the f-string is correctly terminated
                 return f"Could not extract specification details from the response (data type: {type(data).__name__}):\n```text\n{str(data)}\n```"
        else:
            # If data is None, it means parsing failed earlier and returned
            # This case should ideally not be reached due to earlier returns
            return f"Could not process the input. Original input type: {type(input_data).__name__}"

    return markdown

def test_plan_json_to_markdown(input_data):
    """Converts test plan agent response content (ChatMessageContent or str) containing JSON to markdown."""
    json_string = None

    # Extract string content based on input type
    if isinstance(input_data, ChatMessageContent):
        try:
            json_string = str(input_data)
            print(f"Extracted string from ChatMessageContent: {json_string[:100]}...")
        except Exception as e:
            print(f"Error converting ChatMessageContent to string: {e}")
            return f"Error processing agent response object: {e}"
    elif isinstance(input_data, str):
        json_string = input_data
        print(f"Input is already a string: {json_string[:100]}...")
    elif input_data is None:
        json_string = "{}" # Treat None as empty JSON string
        print("Warning: test_plan_json_to_markdown received None input, treating as empty JSON string.")
    else:
        type_name = type(input_data).__name__
        print(f"Warning: test_plan_json_to_markdown received unexpected type: {type_name}")
        return f"Cannot process input of type {type_name}. Expected ChatMessageContent or str."

    if json_string is None:
        print("Warning: json_string is None after type handling, defaulting to empty JSON.")
        json_string = "{}"

    print(f"test_plan_json_to_markdown attempting to parse string: {json_string[:100]}...")
    data = None
    try:
        data = json.loads(json_string)
        print(f"test_plan_json_to_markdown successfully parsed data: {type(data)}")
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON in test_plan_json_to_markdown: {e}")
        escaped_json_string = json_string.replace("`", "\\`")
        return f"Failed to parse the test plan JSON:\n```text\n{escaped_json_string}\n```\n**Error:** {e}"
    except Exception as e: # Catch other potential errors during parsing
        print(f"Unexpected error parsing JSON in test_plan_json_to_markdown: {e}")
        escaped_json_string = json_string.replace("`", "\\`")
        return f"An unexpected error occurred while parsing the test plan:\n```text\n{escaped_json_string}\n```\n**Error:** {e}"

    # --- Markdown generation logic for test plan ---
    markdown = ""
    if isinstance(data, dict):
        plan_name = data.get("name", "Test Plan")
        markdown += f"### {plan_name}\n\n"
        
        # Get test_cases which is now an object where keys are section names and values are lists of test cases
        test_cases_sections = data.get("test_cases", {})
        
        if isinstance(test_cases_sections, dict) and test_cases_sections:
            # Iterate through each section
            for section_name, tests in test_cases_sections.items():
                markdown += f"#### Test Suite: {section_name}\n\n"
                
                if isinstance(tests, list) and tests:
                    for test_case in tests:
                        if isinstance(test_case, dict):
                            # Extract name and description from the test case object
                            test_name = test_case.get("name", "Unnamed Test")
                            test_description = test_case.get("description", "")
                            
                            # Add the test with its name and description
                            markdown += f"- `{test_name}` — {test_description}\n"
                        elif isinstance(test_case, str):
                            # Fallback for simple string test cases
                            markdown += f"- `{test_case}`\n"
                    
                    markdown += "\n"
                else:
                    markdown += "*No test cases found in this section.*\n\n"
        elif isinstance(test_cases_sections, list) and test_cases_sections:
            # Backward compatibility: handle old format where test_cases was a list
            markdown += "#### Test Cases:\n\n"
            for case in test_cases_sections:
                if isinstance(case, str):
                    markdown += f"- `{case}`\n"
            markdown += "\n"
        else:
            markdown += "*No test cases found or 'test_cases' has an unexpected format.*\n"
    else:
        # Fallback if the top level isn't a dictionary
        markdown += "Could not format the test plan as the response was not a JSON object with expected keys ('name', 'test_cases').\n"
        try:
            formatted_json = json.dumps(data, indent=2)
            markdown += f"```json\n{formatted_json}\n```"
        except Exception as dump_error:
            print(f"Error formatting parsed test plan data as JSON: {dump_error}")
            markdown += f"Raw parsed data (type: {type(data).__name__}):\n```text\n{str(data)}\n```"

    return markdown

async def process_with_definition_agent(idea: str, thinking_msg=None):
    """Process the user's idea with the definition agent."""
    definition_agent = cl.user_session.get("definition_agent")
    threads = cl.user_session.get("threads")
    project_state = cl.user_session.get("project_state")

    # Create thinking message if not provided
    if thinking_msg is None:
        thinking_msg = cl.Message(content="Crafting functional specification...", author=DEFINITION_AGENT_NAME)
        await thinking_msg.send()

    thread: ChatHistoryAgentThread = None

    # Get response from definition agent
    response = await definition_agent.get_response(
        messages=f"Create a functional specification for this project idea: {idea}",
        thread=thread
    )
    raw_content = response.content if response.content else "{}"

    # Generate markdown (parsing happens inside)
    markdown_output = json_to_markdown(raw_content)

    # Determine if parsing/conversion was successful
    parsed_json_successfully = not (
        markdown_output.startswith("Failed to parse the specification JSON:") or
        markdown_output.startswith("An unexpected error occurred while parsing the specification:") or
        markdown_output.startswith("Could not extract specific details")
    )

    # Update project state ONLY if parsing was successful and content exists
    if parsed_json_successfully and raw_content != "{}":
        project_state["functional_spec"] = raw_content
        print("Updated functional_spec in project_state (initial creation)")
    else:
        # Do not update spec if parsing failed or content was empty initially
        print(f"Functional spec parsing failed or content empty. Not updating project_state. Markdown output:\n{markdown_output}")
        # Clear potentially invalid spec if it exists
        project_state["functional_spec"] = ""

    cl.user_session.set("project_state", project_state)

    # Store thread for future use
    threads[DEFINITION_AGENT_NAME] = response.thread
    cl.user_session.set("threads", threads)

    # Remove the "crafting functional specification..." message
    await thinking_msg.remove()
    
    # Send a new message with the functional specification result
    functional_spec_msg = cl.Message(content=markdown_output, author=DEFINITION_AGENT_NAME)
    await functional_spec_msg.send()

    # Process with test agent only if successful and spec exists
    if parsed_json_successfully and project_state.get("functional_spec"):
        # Create a new message for test plan phase
        test_plan_msg = cl.Message(content="Creating test plan...", author=TEST_AGENT_NAME)
        await test_plan_msg.send()
        await process_with_test_agent(project_state["functional_spec"], test_plan_msg)
    else:
        await cl.Message(
            content="Skipping test plan generation as the functional specification could not be parsed correctly.",
            author="System"
        ).send()
        # Ask for review, even if spec failed, to give user feedback chance
        await process_with_reviewer_agent()

async def process_with_test_agent(functional_spec: str, thinking_msg=None):
    """Process the functional specification with the test agent."""
    test_agent = cl.user_session.get("test_agent")
    threads = cl.user_session.get("threads")
    
    # Create thinking message if not provided
    if thinking_msg is None:
        thinking_msg = cl.Message(content="Creating test plan...", author=TEST_AGENT_NAME)
        await thinking_msg.send()
    
    # Create a new thread for the test agent
    thread: ChatHistoryAgentThread = None
    
    # Get response from test agent
    response = await test_agent.get_response(messages=f"Create a test plan based on this functional specification: {functional_spec}", thread=thread)
    
    # Get content as string
    response_content = str(response.content) if response.content is not None else "{}"
    
    # Update project state
    project_state = cl.user_session.get("project_state")
    project_state["test_plan"] = response_content
    cl.user_session.set("project_state", project_state)
    
    # Store thread for future use
    threads[TEST_AGENT_NAME] = response.thread
    cl.user_session.set("threads", threads)
    
    # Generate markdown from the JSON response
    markdown_output = test_plan_json_to_markdown(response_content)
    
    # Create a temporary file with the test plan as CSV
    import tempfile
    import os
    import csv
    
    # Create a CSV file with test case names and required headers for Azure DevOps
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv', newline='') as tmp_file:
        csv_writer = csv.writer(tmp_file)
        # Write header with all required fields for Azure DevOps test cases
        csv_writer.writerow(["Work Item Type", "Title", "Test Step", "Step Action", "Step Expected"])
        
        try:
            # Parse the JSON to extract test cases
            test_plan_json = json.loads(response_content)
            test_cases_sections = test_plan_json.get("test_cases", {})
            
            # Check if test_cases is a dictionary (new format) or list (old format)
            if isinstance(test_cases_sections, dict):
                # New format - iterate through each section
                for section_name, tests in test_cases_sections.items():
                    if isinstance(tests, list):
                        for test_case in tests:
                            if isinstance(test_case, dict):
                                # Extract name and description
                                test_name = test_case.get("name", "Unnamed Test")
                                test_description = test_case.get("description", "")
                                # Work Item Type, Title, Description, Test Step, Step Action, Step Expected
                                csv_writer.writerow(["Test Case", test_name, test_description, "", "", ""])
                            elif isinstance(test_case, str):
                                # Fallback for simple string
                                csv_writer.writerow(["Test Case", test_case, "", "", "", ""])
            elif isinstance(test_cases_sections, list):
                # Old format - test_cases is a list of strings
                for test_case in test_cases_sections:
                    if isinstance(test_case, str):
                        # Work Item Type, Title, Description, Test Step, Step Action, Step Expected
                        csv_writer.writerow(["Test Case", test_case, "", "", "", ""])
            
            tmp_file_path = tmp_file.name
        except json.JSONDecodeError:
            # If the content isn't valid JSON, write a message
            csv_writer.writerow(["Test Case", "Invalid JSON response", "Error parsing test plan", "1", "Perform the test", "Expected test result"])
            tmp_file_path = tmp_file.name
    
    # Create a File element to attach to the message
    elements = [
        cl.File(
            name="test_plan.csv",
            path=tmp_file_path,
            display="inline",
        )
    ]

    # Remove the "creating test plan..." message
    await thinking_msg.remove()
    
    # Send a new message with the test plan result
    test_plan_msg = cl.Message(content=markdown_output, author=TEST_AGENT_NAME, elements=elements)
    await test_plan_msg.send()
    
    # Now process with reviewer agent - create a new message for review phase
    review_msg = cl.Message(content="Reviewing specification and test plan...", author=REVIEWER_AGENT_NAME)
    await review_msg.send()
    await process_with_reviewer_agent(review_msg)

@cl.action_callback("upload_to_azure_devops")
async def on_upload_to_azure_devops(action):
    """Handle action to upload test plan to Azure DevOps."""
    tmp_file_path = action.payload.get("file_path", "")
    
    # Process with Azure DevOps agent
    await process_with_azure_devops_agent("Please create a new Azure DevOps project")
    
    # Clean up the temporary file
    try:
        os.unlink(tmp_file_path)
    except:
        pass  # Ignore errors during cleanup
    
    # Remove the action buttons
    await action.remove()

@cl.action_callback("skip_upload")
@cl.action_callback("skip_integration")
async def on_skip_upload(action):
    """Handle action to skip uploading test plan to Azure DevOps."""
    await cl.Message(content="Continuing without uploading to Azure DevOps.", author="System").send()
    
    # Clean up the temporary file if path is in the payload
    file_path = action.payload.get("file_path", "")
    if file_path:
        try:
            os.unlink(file_path)
        except:
            pass  # Ignore errors during cleanup
    
    # Remove the action buttons
    await action.remove()

async def process_with_reviewer_agent(thinking_msg=None):
    """Process the functional specification and test plan with the reviewer agent."""
    reviewer_agent = cl.user_session.get("reviewer_agent")
    threads = cl.user_session.get("threads")
    project_state = cl.user_session.get("project_state")
    
    if thinking_msg is None:
        thinking_msg = cl.Message(content="Reviewing specification and test plan...", author=REVIEWER_AGENT_NAME)
        await thinking_msg.send()
    
    # Create a new thread for the reviewer agent
    thread: ChatHistoryAgentThread = None
    
    # Get response from reviewer agent
    response = await reviewer_agent.get_response(
        messages=f"""Review the following functional specification and test plan:
        
Functional Specification:
{project_state['functional_spec']}

Test Plan:
{project_state['test_plan']}
""",
        thread=thread
    )
    
    # Update project state
    response_content = str(response.content) if response.content is not None else ""
    project_state["review_feedback"] = response_content
    cl.user_session.set("project_state", project_state)
    
    # Store thread for future use
    threads[REVIEWER_AGENT_NAME] = response.thread
    cl.user_session.set("threads", threads)

    # Remove the "reviewing..." message
    await thinking_msg.remove()
    
    # Try to parse the JSON response
    try:
        # First, check if the content string actually resembles JSON
        if response_content.strip().startswith("{") and response_content.strip().endswith("}"):
            review_data = json.loads(response_content)
            
            # Extract actionable suggestions if available
            actionable_suggestions = review_data.get("actionable_suggestions", [])
            actionable_suggestions_presentation = review_data.get("actionable_suggestions_message_presentation", "")
            
            # Create action buttons for each suggestion
            actions = []
            for i, suggestion in enumerate(actionable_suggestions):
                if i < 6:  # Limit to 5 suggestions as we have 5 callbacks
                    actions.append(
                        cl.Action(
                            name=f"apply_suggestion_{i}",
                            payload={"suggestion": suggestion},
                            label=suggestion
                        )
                    )

            # Send response to user with action buttons
            if actions:
                await cl.Message(content=actionable_suggestions_presentation, author=REVIEWER_AGENT_NAME, actions=actions).send()
            else:
                await cl.Message(content=response_content, author=REVIEWER_AGENT_NAME).send()
        else:
            # Not JSON formatted, send as plain text
            await cl.Message(content=response_content, author=REVIEWER_AGENT_NAME).send()
    except json.JSONDecodeError:
        # If not valid JSON, send the response without actions
        await cl.Message(content=response_content, author=REVIEWER_AGENT_NAME).send()
    except Exception as e:
        # Log any other errors and still show the response
        print(f"Error processing reviewer response: {str(e)}")
        await cl.Message(content=response_content, author=REVIEWER_AGENT_NAME).send()
    
    # Ask user for their feedback
    await cl.Message(
        content="Would you like to set up this project on Azure DevOps, or ask for changes?",
        author="System",
        actions=[
            cl.Action(
                name="approve_spec",
                label="Set up project",
                payload={"message": "Approve"}
            )
        ]
    ).send()

async def handle_revision_request(content: str):
    """Handle user requests for revisions using the triage agent."""
    project_state = cl.user_session.get("project_state")
    threads = cl.user_session.get("threads")
    triage_agent = cl.user_session.get("triage_agent")

    # Get the triage agent thread or create one if it doesn't exist
    triage_thread = threads.get(TRIAGE_AGENT_NAME)

    thinking_msg = cl.Message(content="Analyzing revision request...", author=TRIAGE_AGENT_NAME)
    await thinking_msg.send()

    # Prompt for triage agent to classify the revision request
    triage_prompt = f"""
    Analyze the following user revision request and determine if it applies to the functional specification or the test plan:

    User Request: {content}

    Current Project State:
    - Has Functional Spec: {"Yes" if project_state.get("functional_spec") else "No"}
    - Has Test Plan: {"Yes" if project_state.get("test_plan") else "No"}

    Respond with one of the following:
    - "REVISE_FUNCTIONAL_SPEC" if the request is to revise the functional specification.
    - "REVISE_TEST_PLAN" if the request is to revise the test plan.
    - "SMALL_TALK" if this is small talk, greeting, or asking about system capabilities.
    - "UNKNOWN" if the target for revision is unclear.
    """

    try:
        triage_response = await triage_agent.get_response(
            messages=triage_prompt,
            thread=triage_thread
        )

        # Update triage thread
        threads[TRIAGE_AGENT_NAME] = triage_response.thread
        cl.user_session.set("threads", threads)

        decision = str(triage_response.content).strip().upper()

        if "REVISE_FUNCTIONAL_SPEC" in decision:
            # Update the thinking message for functional spec revision
            thinking_msg.content = "Revising functional specification..."
            thinking_msg.author = DEFINITION_AGENT_NAME
            await thinking_msg.update()
            await _process_revision_definition(content, thinking_msg)
        elif "REVISE_TEST_PLAN" in decision:
            # Update the thinking message for test plan revision
            thinking_msg.content = "Revising test plan..."
            thinking_msg.author = TEST_AGENT_NAME
            await thinking_msg.update()
            await _process_revision_test_plan(content, thinking_msg)
        elif "SMALL_TALK" in decision:
            await handle_small_talk(content)
        else:
            # If triage is unclear, handle as general feedback for now
            await cl.Message(
                content=f"Could not determine the target for revision. Treating as general feedback: {content}",
                author="System"
            ).send()
            await handle_general_feedback(content) # Or potentially route differently

    except Exception as e:
        print(f"Error during triage for revision: {e}")
        await cl.Message(
            content=f"An error occurred while analyzing your revision request: {e}. Please try rephrasing.",
            author="System"
        ).send()

async def _process_revision_definition(content: str, thinking_msg=None):
    """Process revision for functional specification."""
    project_state = cl.user_session.get("project_state")
    definition_agent = cl.user_session.get("definition_agent")
    threads = cl.user_session.get("threads")
    thread = threads.get(DEFINITION_AGENT_NAME)

    # Create thinking message if not provided
    if thinking_msg is None:
        thinking_msg = cl.Message(content="Revising functional specification...", author=DEFINITION_AGENT_NAME)
        await thinking_msg.send()

    # Get response from definition agent
    response = await definition_agent.get_response(
        messages=f"Revise the functional specification based on this feedback: {content}. Here is the current specification: {project_state.get('functional_spec', 'None')}",
        thread=thread
    )
    raw_content = response.content if response.content else "{}"

    # Generate markdown (parsing happens inside)
    markdown_output = json_to_markdown(raw_content)

    # Determine if parsing/conversion was successful
    parsed_json_successfully = not (
        markdown_output.startswith("Failed to parse the specification JSON:") or
        markdown_output.startswith("An unexpected error occurred while parsing the specification:") or
        markdown_output.startswith("Could not extract specific details")
    )

    # Update project state ONLY if parsing was successful and content exists
    if parsed_json_successfully and raw_content != "{}":
        project_state["functional_spec"] = raw_content
        print("Updated functional_spec in project_state (revision)")
    else:
        # Do not update spec if parsing failed or content was empty during revision
        print(f"Functional spec parsing failed or content empty during revision. Not updating project_state. Markdown output:\n{markdown_output}")
        # Keep the old spec in this case? Or clear it? Let's keep the old one.
        # project_state["functional_spec"] remains unchanged

    cl.user_session.set("project_state", project_state)

    # Update thread
    threads[DEFINITION_AGENT_NAME] = response.thread
    cl.user_session.set("threads", threads)

    # Remove the "revising functional specification..." message
    await thinking_msg.remove()
    
    # Send a new message with the revised functional specification
    functional_spec_msg = cl.Message(content=markdown_output, author=DEFINITION_AGENT_NAME)
    await functional_spec_msg.send()

    # Update test plan only if spec was successfully updated and exists
    if parsed_json_successfully and project_state.get("functional_spec"):
        # Create a new message for test plan revision
        test_plan_msg = cl.Message(content="Creating test plan...", author=TEST_AGENT_NAME)
        await test_plan_msg.send()
        await process_with_test_agent(project_state["functional_spec"], test_plan_msg)
    else:
        await cl.Message(
            content="Skipping test plan update as the functional specification could not be updated correctly.",
            author="System"
        ).send()
        # Ask for review again
        await process_with_reviewer_agent()

async def _process_revision_test_plan(content: str, thinking_msg=None):
    """Process revision for test plan."""
    project_state = cl.user_session.get("project_state")
    test_agent = cl.user_session.get("test_agent")
    threads = cl.user_session.get("threads")
    thread = threads.get(TEST_AGENT_NAME)

    # Create thinking message if not provided
    if thinking_msg is None:
        thinking_msg = cl.Message(content="Revising test plan...", author=TEST_AGENT_NAME)
        await thinking_msg.send()

    # Get response from test agent
    response = await test_agent.get_response(
        messages=f"Revise the test plan based on this feedback: {content}. Here is the current test plan: {project_state['test_plan']} and the functional specification: {project_state['functional_spec']}",
        thread=thread
    )
    
    # Convert content to string
    raw_content = str(response.content) if response.content is not None else "{}"

    # Update project state with the raw JSON response
    project_state["test_plan"] = raw_content
    cl.user_session.set("project_state", project_state)

    # Update thread
    threads[TEST_AGENT_NAME] = response.thread
    cl.user_session.set("threads", threads)

    # Generate markdown from the JSON response
    markdown_output = test_plan_json_to_markdown(raw_content)

    # Create a temporary file with the test plan as CSV
    import tempfile
    import os
    import csv
    
    # Create a CSV file with test case names and required headers for Azure DevOps
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv', newline='') as tmp_file:
        csv_writer = csv.writer(tmp_file)
        # Write header with all required fields for Azure DevOps test cases
        csv_writer.writerow(["Work Item Type", "Title", "Test Step", "Step Action", "Step Expected"])
        
        try:
            # Parse the JSON to extract test cases
            test_plan_json = json.loads(raw_content)
            test_cases_sections = test_plan_json.get("test_cases", {})
            
            # Check if test_cases is a dictionary (new format) or list (old format)
            if isinstance(test_cases_sections, dict):
                # New format - iterate through each section
                for section_name, tests in test_cases_sections.items():
                    if isinstance(tests, list):
                        for test_case in tests:
                            if isinstance(test_case, dict):
                                # Extract name and description
                                test_name = test_case.get("name", "Unnamed Test")
                                #test_description = test_case.get("description", "")
                                # Work Item Type, Title, Description, Test Step, Step Action, Step Expected
                                csv_writer.writerow(["Test Case", test_name, "", "", ""])
                            elif isinstance(test_case, str):
                                # Fallback for simple string
                                csv_writer.writerow(["Test Case", test_case, "", "", "", ""])
            elif isinstance(test_cases_sections, list):
                # Old format - test_cases is a list of strings
                for test_case in test_cases_sections:
                    if isinstance(test_case, str):
                        # Work Item Type, Title, Description, Test Step, Step Action, Step Expected
                        csv_writer.writerow(["Test Case", test_case, "", "", "", ""])
            
            tmp_file_path = tmp_file.name
        except json.JSONDecodeError:
            # If the content isn't valid JSON, write a message
            csv_writer.writerow(["Test Case", "Invalid JSON response", "1", "Perform the test", "Expected test result"])
            tmp_file_path = tmp_file.name
    
    # Create a File element to attach to the message
    elements = [
        cl.File(
            name="test_plan.csv",
            path=tmp_file_path,
            display="inline",
        )
    ]

    # Remove the "revising test plan..." message
    await thinking_msg.remove()
    
    # Send a new message with the revised test plan
    test_plan_msg = cl.Message(content=markdown_output, author=TEST_AGENT_NAME, elements=elements)
    await test_plan_msg.send()
    
    # Clean up the temporary file after sending
    try:
        os.unlink(tmp_file_path)
    except:
        pass  # Ignore errors during cleanup

    # Review both updated documents - create a new message for the review phase
    review_msg = cl.Message(content="Reviewing specification and test plan...", author=REVIEWER_AGENT_NAME)
    await review_msg.send()
    await process_with_reviewer_agent(review_msg)

async def handle_small_talk(content: str):
    """Handle small talk, greetings, or questions about system capabilities."""
    triage_agent = cl.user_session.get("triage_agent")
    threads = cl.user_session.get("threads")
    thread = threads.get(TRIAGE_AGENT_NAME)
    project_state = cl.user_session.get("project_state")
    
    # Get the current state of the project
    has_functional_spec = bool(project_state.get("functional_spec"))
    has_test_plan = bool(project_state.get("test_plan"))
    is_approved = project_state.get("is_approved", False)
    
    # Prepare prompt for triage agent to handle small talk
    small_talk_prompt = f"""
    The user has sent a message that appears to be small talk or a question about system capabilities: "{content}"
    
    Current Project State:
    - Has Functional Spec: {"Yes" if has_functional_spec else "No"}
    - Has Test Plan: {"Yes" if has_test_plan else "No"}
    - Is Approved: {"Yes" if is_approved else "No"}
    - Project Idea: {project_state.get("idea", "Not provided yet")}
    
    Session Progress:
    - Started with idea: {project_state.get("idea", "Not provided yet")}
    - Current stage: {"Project approved and ready for implementation" if is_approved else "Specification complete, waiting for test plan" if has_functional_spec and not has_test_plan else "Specification and test plan complete, waiting for review/approval" if has_functional_spec and has_test_plan and not is_approved else "Waiting for project idea" if not has_functional_spec else "In progress"}
    - Next steps: {"Implementation can begin or integrate with Azure DevOps" if is_approved else "Create test plan" if has_functional_spec and not has_test_plan else "Review and approve specification and test plan" if has_functional_spec and has_test_plan and not is_approved else "Provide a project idea" if not has_functional_spec else "Continue with current stage"}
    
    Please respond appropriately to the user's message. Some guidelines:
    
    1. If it's a greeting, respond with a friendly greeting and offer assistance with their project.
    2. If they're asking what the system can do, explain the collaborative specification system:
       - I help users create a complete software project specification
       - I use multiple specialized agents: definition, test planning, reviewer, code generation, and Azure DevOps integration
       - The process: define project requirements → create test plan → review and refine → approve → optionally integrate with Azure DevOps or generate code
    3. If they're asking about the current status of their project, give them a summary based on the current state.
       - If they have a functional spec, mention that it's created
       - If they have a test plan, mention that it's created
       - If the project is approved, mention that it's ready for implementation or Azure DevOps integration
       - If they're in the middle of the process, tell them what the next step is
    4. If they're asking about chat history or what has happened so far, summarize the current project state.
    5. Always maintain a helpful, friendly tone.
    
    Do not mention anything about being an AI or any technical details about how you function.
    """
    
    # Get response from triage agent
    response = await triage_agent.get_response(
        messages=small_talk_prompt,
        thread=thread
    )
    
    # Update thread
    threads[TRIAGE_AGENT_NAME] = response.thread
    cl.user_session.set("threads", threads)
    
    print("TYPE OF RESPONSE:", type(response))
    print("TYPE OF CONTENT:", type(response.content))

    # Send response to user
    await cl.Message(content=str(response.content), author="System").send()

async def handle_general_feedback(content: str):
    """Handle general feedback or questions from the user."""
    # For simplicity, we'll just pass this to the reviewer agent
    reviewer_agent = cl.user_session.get("reviewer_agent")
    threads = cl.user_session.get("threads")
    thread = threads.get(REVIEWER_AGENT_NAME)
    project_state = cl.user_session.get("project_state")
    
    # Get response from reviewer agent
    response = await reviewer_agent.get_response(
        messages=f"""The user has provided this feedback or question: {content}
        
Functional Specification:
{project_state['functional_spec']}

Test Plan:
{project_state['test_plan']}

Previous Review Feedback:
{project_state['review_feedback']}

Please respond appropriately.
""",
        thread=thread
    )
    
    # Send response to user
    await cl.Message(content=response.content, author=REVIEWER_AGENT_NAME).send()

async def process_with_azure_devops_agent(content: str):
    """Process the user's request with the Azure DevOps agent."""
    settings = cl.user_session.get("settings")
    threads = cl.user_session.get("threads")
    project_state = cl.user_session.get("project_state")
    
    org_url = settings.get("OrgURL", "")
    pat = settings.get("PAT", "")
    
    if not org_url or not pat:
        await cl.Message(
            content="To use Azure DevOps integration, please provide your organization URL and PAT in the settings.",
            author="System"
        ).send()
        return
    
    try:
        # Create the Azure DevOps agent directly instead of retrieving from session
        azure_devops_agent = await create_azure_devops_agent(
            AZURE_DEVOPS_AGENT_NAME,
            AZURE_DEVOPS_AGENT_INSTRUCTIONS,
            org_url=org_url,
            pat=pat
        )
    except Exception as e:
        await cl.Message(
            content=f"Error initializing Azure DevOps agent: {str(e)}. Please check your settings and ensure the MCP server is running.",
            author="System"
        ).send()
        return
    
    # Create a status message that will be updated throughout the process
    status_msg = cl.Message(content="Processing Azure DevOps request...", author=AZURE_DEVOPS_AGENT_NAME)
    await status_msg.send()
    
    # Check if we have a thread for the Azure DevOps agent
    if AZURE_DEVOPS_AGENT_NAME not in threads:
        threads[AZURE_DEVOPS_AGENT_NAME] = None
    
    # Prepare context for the Azure DevOps agent
    # Generate a suitable project name from the idea
    project_idea = project_state.get("idea", "")
    
    try:
        # Provide explicit instructions for project creation with proper parameter names
        prompt = f"""
        I need you to create an Azure DevOps project.

        Based on the project idea, generate a project name and a short description.

        Idea: {project_idea}
        org_url="{org_url}",
        pat="{pat}"

        Respond in a JSON, with the following keys:
        - message: in one line with a concise, professional message confirming the creation of the new Azure DevOps project, including the project name and its URL. Example: "New Azure DevOps project **<PROJECT_NAME>** created successfully! Access it at <PROJECT_URL>"
        - project_name: the name of the new Azure DevOps project. (The name should not contain spaces or special characters)
        - project_url: the URL of the new Azure DevOps project
        """
        
        # Get response from Azure DevOps agent
        response = await azure_devops_agent.get_response(
            messages=prompt,
            thread=threads[AZURE_DEVOPS_AGENT_NAME]
        )
        
        # Store thread for future interactions
        threads[AZURE_DEVOPS_AGENT_NAME] = response.thread
        cl.user_session.set("threads", threads)

        response_data = json.loads(str(response.content))
        print("RESPONSE DATA:", response_data)
        print("PROJECT NAME:", response_data['project_name'])
        print("PROJECT URL:", response_data['project_url'])
        
        # Set the project name and URL in the project state
        project_state["azure_devops_project_name"] = response_data['project_name']
        project_state["azure_devops_project_url"] = response_data['project_url']
        cl.user_session.set("project_state", project_state)

        # Update status message with project creation response
        #status_msg.content = str(response_data['message'])
        #await status_msg.update()

        project_creation_msg = str(response_data['message'])
        
        # Create work items from functional spec if available
        print("FUNCTIONAL SPEC:", project_state.get("functional_spec"))
        if not project_state.get("functional_spec"):
            print("FUNCTIONAL SPEC IS EMPTY")
        else:
            print("FUNCTIONAL SPEC IS NOT EMPTY")

        if project_state.get("functional_spec"):
            # Update status message for work item creation
            status_msg.content = "Creating work items from functional specification..."
            await status_msg.update()
            
            # Create work items based on functional specification
            work_items_prompt = f"""
            I need you to create a Product Backlog Item in the Azure DevOps project "{project_state['azure_devops_project_name']}" based on this functional specification.
            
            The functional specification is in JSON format. Parse it and create an Product Backlog Item work item, use the same content as description.
            
            Functional Specification:
            {project_state['functional_spec']}
            
            org_url="{org_url}",
            pat="{pat}",
            project="{project_state['azure_devops_project_name']}"
            
            Respond with a brief confirmation of the work items created.
            """
            
            # Get response for work item creation
            work_items_response = await azure_devops_agent.get_response(
                messages=work_items_prompt,
                thread=threads[AZURE_DEVOPS_AGENT_NAME]
            )
            
            # Update thread
            threads[AZURE_DEVOPS_AGENT_NAME] = work_items_response.thread
            cl.user_session.set("threads", threads)
            
            # Update status message with work items creation response
            #status_msg.content = str(work_items_response.content)
            #await status_msg.update()

            work_item_creation_msg = str(work_items_response.content)
            
            # Now create test cases from test plan if available
            if project_state.get("test_plan"):
                # Update status message for test case creation
                status_msg.content = "Creating test cases from test plan..."
                await status_msg.update()
                
                # Create test cases based on test plan
                test_cases_prompt = f"""
                I need you to create a single test plan in the Azure DevOps project "{project_state['azure_devops_project_name']}" based on this test plan.
                
                The test plan is in JSON format. Parse it and create test cases for each test described. Use only the test names, not the description.
                
                All test cases should be in the same test suite.

                Test Plan:
                {project_state['test_plan']}
                
                org_url="{org_url}",
                pat="{pat}",
                project="{project_state['azure_devops_project_name']}"
                
                Respond with a brief confirmation of the test cases created.
                """
                
                # Get response for test case creation
                test_cases_response = await azure_devops_agent.get_response(
                    messages=test_cases_prompt,
                    thread=threads[AZURE_DEVOPS_AGENT_NAME]
                )
                
                # Update thread
                threads[AZURE_DEVOPS_AGENT_NAME] = test_cases_response.thread
                cl.user_session.set("threads", threads)
                
                test_cases_msg = str(test_cases_response.content)

                # Update status message with test cases creation response
                #status_msg.content = str(test_cases_response.content)
                #await status_msg.update()

                # Update final message
                final_prompt = f"""
                Project creation result:                
                {project_creation_msg}
                
                Work item creation result:                
                {work_item_creation_msg}
                
                Test case creation result:                
                {test_cases_msg}

                Produce a one line summary of the work done. (Use markdown for link of the project URL). You can add and the end something like "access it [here](here would be the link)."
                """

                final_response = await azure_devops_agent.get_response(
                    messages=final_prompt,
                    thread=threads[AZURE_DEVOPS_AGENT_NAME]
                )

                # Update thread
                threads[AZURE_DEVOPS_AGENT_NAME] = final_response.thread
                cl.user_session.set("threads", threads)

                # Update status message with final response
                status_msg.content = str(final_response.content)
                await status_msg.update()
        
    except Exception as e:
        # Update status message with error
        status_msg.content = f"Error during Azure DevOps integration: {str(e)}"
        await status_msg.update()
    finally:
        # Always disconnect the plugin to clean up
        if hasattr(azure_devops_agent, '_mcp_plugin'):
            try:
                if hasattr(azure_devops_agent._mcp_plugin, 'disconnect'):
                    await azure_devops_agent._mcp_plugin.disconnect()
                else:
                    # Plugin doesn't have disconnect method, log and continue
                    print("Note: MCPSsePlugin doesn't have a disconnect method")
            except Exception as e:
                print(f"Error disconnecting MCP plugin: {str(e)}")
        
        # Ask the user if they would like to implement the project
        await cl.Message(
            content="Would you like to generate the code for this project now?",
            author="System",
            actions=[
                cl.Action(
                    name="implement_project",
                    label="Generate code",
                    description="Start implementing the project by generating code",
                    payload={}
                )
            ]
        ).send()

@cl.action_callback("implement_project")
async def on_implement_project(action):
    """Handle action to implement the project."""
    project_state = cl.user_session.get("project_state")
    threads = cl.user_session.get("threads")
    
    # Create a status message that will be updated throughout the process
    status_msg = cl.Message(content="Starting project implementation...", author="System")
    await status_msg.send()
    
    try:
        # Create the Job Launcher agent
        job_launcher_agent = await create_job_launcher_agent(
            JOB_LAUNCHER_AGENT_NAME,
            JOB_LAUNCHER_AGENT_INSTRUCTIONS
        )
        
        # Update status message to show we're launching the code agent
        status_msg.content = "Code Agent has been launched and is implementing your project..."
        status_msg.author = JOB_LAUNCHER_AGENT_NAME
        await status_msg.update()
        
        # Check if we have a thread for the Job Launcher agent
        if JOB_LAUNCHER_AGENT_NAME not in threads:
            threads[JOB_LAUNCHER_AGENT_NAME] = None
        
        # Get settings
        settings = cl.user_session.get("settings", {})
        code_agent = settings.get("CodeAgent", "Claude Code (Anthropic)")

        # Get the code agent name
        # If the code agent is "Claude Code (Anthropic)", then the code agent name is "claude-code"
        # If the code agent is "Codex (OpenAI)", then the code agent name is "codex"
        code_agent_name = "claude-code" if code_agent == "Claude Code (Anthropic)" else "codex"
 
        # Prepare context for the Job Launcher agent
        prompt = f"""
        I need you to implement a project based on this functional specification and test plan.
        
        Project Name: <project_name>{project_state.get("azure_devops_project_name", "")}</project_name>
        
        # Azure DevOps credentials
        org_url="{settings.get('OrgURL', '')}",
        pat="{settings.get('PAT', '')}",
        
        Functional Specification:
        <functional_spec>{project_state.get("functional_spec", "")}</functional_spec>
        
        Test Plan:
        <test_plan>{project_state.get("test_plan", "")}</test_plan>
        
        Preferred Code Agent: <code_agent>{code_agent_name}</code_agent>

        Job Type: "implementation"
        
        Use the launch_code_job tool to start the code generation.
        Return a one sentence message.
        """
        
        # Get first response from agent - this should trigger the job
        response = await job_launcher_agent.get_response(
            messages=prompt,
            thread=threads[JOB_LAUNCHER_AGENT_NAME]
        )
        
        # Update status message with the initial response
        status_msg.content = str(response.content)
        await status_msg.update()
        
        # Store thread for future interactions
        threads[JOB_LAUNCHER_AGENT_NAME] = response.thread
        cl.user_session.set("threads", threads)
        
        # Call Azure DevOps agent to get the latest commit
        settings = cl.user_session.get("settings", {})
        project_name = project_state.get("azure_devops_project_name", "")
        org_url = settings.get("OrgURL", "")
        pat = settings.get("PAT", "")
        
        if project_name and org_url and pat:
            try:
                # Create Azure DevOps agent
                azure_devops_agent = await create_azure_devops_agent(
                    AZURE_DEVOPS_AGENT_NAME,
                    AZURE_DEVOPS_AGENT_INSTRUCTIONS,
                    org_url=org_url,
                    pat=pat
                )
                
                # Check if we have a thread for the Azure DevOps agent
                if AZURE_DEVOPS_AGENT_NAME not in threads:
                    threads[AZURE_DEVOPS_AGENT_NAME] = None
                
                # Get latest commit information
                commit_prompt = f"""
                I need to get the latest commit information for the Azure DevOps project.
    
                org_url="{org_url}",
                pat="{pat}",
                project="{project_name}"

                Return a one line message like: the lastest commit is... include branch name and commit id. Use markdown code blocks in linefor the branch name and commit id. Include the links to the branch and commit id with markdown, like branch-name (view link) and commit-id (view link).
                """
                
                # Get response
                commit_response = await azure_devops_agent.get_response(
                    messages=commit_prompt,
                    thread=threads[AZURE_DEVOPS_AGENT_NAME]
                )
                
                # Update thread
                threads[AZURE_DEVOPS_AGENT_NAME] = commit_response.thread
                cl.user_session.set("threads", threads)
                
                # Show the latest commit information
                await cl.Message(
                    content=str(commit_response.content),
                    author=AZURE_DEVOPS_AGENT_NAME
                ).send()
                
                # Clean up Azure DevOps agent
                if hasattr(azure_devops_agent, '_mcp_plugin'):
                    try:
                        if hasattr(azure_devops_agent._mcp_plugin, 'disconnect'):
                            await azure_devops_agent._mcp_plugin.disconnect()
                    except Exception as e:
                        print(f"Error disconnecting Azure DevOps MCP plugin: {str(e)}")
            except Exception as e:
                print(f"Error getting commit information: {str(e)}")
                # Continue with the flow even if getting commit information fails
        
        # Add a new project message after job is launched - separate from the job response
        await prompt_for_new_project()
    
    except Exception as e:
        # Update status message with error
        status_msg.content = f"Error during project implementation: {str(e)}"
        await status_msg.update()
    finally:
        # Always disconnect the plugin to clean up
        if 'job_launcher_agent' in locals() and hasattr(job_launcher_agent, '_mcp_plugin'):
            try:
                if hasattr(job_launcher_agent._mcp_plugin, 'disconnect'):
                    await job_launcher_agent._mcp_plugin.disconnect()
                else:
                    # Plugin doesn't have disconnect method, log and continue
                    print("Note: MCPSsePlugin doesn't have a disconnect method")
            except Exception as e:
                print(f"Error disconnecting MCP plugin: {str(e)}")
    
    # Remove the action buttons
    await action.remove()

async def prompt_for_new_project():
    """Send a separate message asking if the user wants to start a new project."""
    # This function is separate from the implementation flow, ensuring it runs independently
    await cl.Message(
        content="Your project is all set! Tell me about a new idea you'd like to start",
        author="System"
    ).send()
    
    # Reset the triage agent thread to ensure proper handling of the next user message
    threads = cl.user_session.get("threads", {})
    if TRIAGE_AGENT_NAME in threads:
        # Don't reset the thread, just ensure it's accessible
        print(f"Triage agent thread exists, ready for new project handling")
    else:
        print(f"No triage agent thread found, will create one on next message")

@cl.on_settings_update
async def setup_agent(settings):
    print("on_settings_update", settings)
    # Store updated settings in the user session
    cl.user_session.set("org_url", settings.get("OrgURL"))
    cl.user_session.set("pat", settings.get("PAT"))
    
    print(f"Organization URL set to: {settings.get('OrgURL')}")
    print(f"PAT has been updated.") # Avoid printing the PAT itself 

@cl.action_callback("integrate_with_azure_devops")
async def on_integrate_with_azure_devops(action):
    """Handle action to integrate with Azure DevOps."""
    project_state = cl.user_session.get("project_state")
    settings = cl.user_session.get("settings")
    
    # Get organization URL and PAT from settings
    org_url = settings.get("OrgURL", "")
    pat = settings.get("PAT", "")
    
    # Process with Azure DevOps agent to create project and work items
    await process_with_azure_devops_agent("Please create a new Azure DevOps project using my organization settings and populate it with work items from the functional specification and test plan")
    
    # Remove the action buttons
    await action.remove()

@cl.action_callback("skip_integration")
async def on_skip_integration(action):
    """Handle action to skip Azure DevOps integration."""
    await cl.Message(content="Continuing without Azure DevOps integration. Your project specification and test plan are approved and ready for implementation.", author="System").send()
    
    # Remove the action buttons
    await action.remove()
    
    # Ask the user if they would like to implement the project
    await cl.Message(
        content="Would you like to implement this project (generate code) now?",
        author="System",
        actions=[
            cl.Action(
                name="implement_project",
                label="Yes, implement project",
                description="Start implementing the project by generating code",
                payload={}
            )
        ]
    ).send() 