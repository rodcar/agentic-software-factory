# Collaborative Project Specification System

A multi-agent system built with Semantic Kernel and Chainlit that helps define software project specifications and test plans through collaborative AI agents.

## Features

- **Project Definition Agent**: Creates comprehensive functional specifications
- **Test Planning Agent**: Develops detailed test plans aligned with functional requirements
- **Reviewer Agent**: Reviews documents for quality and suggests improvements
- **Interactive User Experience**: Chat-based interface for requesting revisions and providing feedback
- **Azure OpenAI Integration**: Primarily uses Azure OpenAI Service with optional OpenAI API support

## Installation

1. Clone this repository:
```
git clone <repository-url>
cd collaborative-spec-system
```

2. Install the required dependencies:
```
pip install -r requirements.txt
```

3. Configure environment variables:
   - Copy `.env.example` to `.env`
   - Add your Azure OpenAI Service details to the `.env` file

## Running the Application

### Setup Environment Variables

1. Open the `.env` file in a text editor and configure your AI service credentials:

   **For Azure OpenAI Service (default):**
   ```
   USE_AZURE=true
   AZURE_OPENAI_API_KEY=your-actual-azure-api-key
   AZURE_OPENAI_ENDPOINT=https://your-resource-name.openai.azure.com/
   AZURE_OPENAI_DEPLOYMENT_NAME=your-actual-deployment-name
   ```

   **For OpenAI API (alternative):**
   ```
   USE_AZURE=false
   OPENAI_API_KEY=your-actual-openai-api-key
   OPENAI_CHAT_MODEL_ID=gpt-4
   ```

### Start the Application

1. Ensure you're in the project directory:
   ```
   cd collaborative-spec-system
   ```

2. Start the Chainlit server:
   ```
   chainlit run collaborative_spec_system.py
   ```

3. The terminal will display a URL (typically http://localhost:8000)

4. Open the URL in your web browser to access the application

### Troubleshooting

- **Missing Environment Variables**: If you see error messages about missing variables, check your `.env` file to ensure all required credentials are properly set.
- **Connection Errors**: Verify that your API keys and endpoints are correct and that you have internet connectivity.
- **Azure OpenAI Deployment**: Ensure your Azure OpenAI deployment name corresponds to a valid deployment in your Azure account.
- **Port Conflicts**: If port 8000 is already in use, Chainlit will attempt to use a different port. Check the terminal output for the correct URL.

## Usage

1. When the application loads in your browser, you'll be greeted with a welcome message

2. Share your project idea in the chat input box at the bottom of the screen

3. The agents will collaborate to create your project specification and test plan:
   - The Project Definition Agent will draft a functional specification
   - The Test Planning Agent will create a test plan based on the specification
   - The Reviewer Agent will review both documents for quality

4. Review the outputs displayed in the chat thread

5. Request revisions by typing messages like "Please revise the functional specification to include..." or "The test plan should be updated to..."

6. When satisfied with the documents, approve them by typing "approve" or "accept"

## Agent Workflow

1. User provides project idea
2. Project Definition Agent creates functional specification
3. Test Planning Agent creates test plan based on specification
4. Reviewer Agent reviews both documents for quality
5. User can request revisions or approve documents
6. If revisions are requested, relevant agents update their documents
7. Cycle continues until user approves

## Configuration Options

### Azure OpenAI Service (Default)
To use Azure OpenAI Service (default configuration), set the following in your `.env` file:
```
USE_AZURE=true
AZURE_OPENAI_API_KEY=your-azure-openai-api-key
AZURE_OPENAI_ENDPOINT=https://your-resource-name.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT_NAME=your-deployment-name
```

### OpenAI API
To use the OpenAI API instead of Azure OpenAI, set the following in your `.env` file:
```
USE_AZURE=false
OPENAI_API_KEY=your-openai-api-key
OPENAI_CHAT_MODEL_ID=gpt-4
```

## Environment Variables

- `USE_AZURE`: Set to "true" to use Azure OpenAI Service (default) or "false" to use OpenAI API
- `AZURE_OPENAI_API_KEY`: Your Azure OpenAI API key
- `AZURE_OPENAI_ENDPOINT`: Your Azure OpenAI endpoint URL
- `AZURE_OPENAI_DEPLOYMENT_NAME`: Your Azure OpenAI deployment name
- `OPENAI_API_KEY`: Your OpenAI API key (only used when USE_AZURE=false)
- `OPENAI_CHAT_MODEL_ID`: The model ID to use with OpenAI API (default: gpt-4)

## License

[MIT License](LICENSE) 