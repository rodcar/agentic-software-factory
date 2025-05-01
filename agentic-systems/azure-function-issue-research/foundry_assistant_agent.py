from autogen_agentchat.agents import BaseChatAgent
from autogen_agentchat.base import Response
from autogen_agentchat.messages import BaseChatMessage, TextMessage
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential


from typing import Sequence


class FoundryAssistantAgent(BaseChatAgent):
    def __init__(self, agent_id, conn_str, **kwargs):
        super().__init__(**kwargs)
        self.agent_name = kwargs.get("name","FoundryAssistantAgent")
        self.agent_id = agent_id
        self.conn_str = conn_str
        self.credential = DefaultAzureCredential()
        self.project_client = AIProjectClient.from_connection_string(
            credential=self.credential,
            conn_str=self.conn_str
        )
        self.thread = self.project_client.agents.create_thread()
        self._message_history: List[BaseChatMessage] = []

    async def on_messages(self, messages: Sequence[BaseChatMessage], sender, config=None):
        self._message_history.extend(messages)
        prompt = messages[-1].content if messages else ""
        self.project_client.agents.create_message(
            thread_id=self.thread.id,
            role="user",
            content=prompt
        )
        self.project_client.agents.create_and_process_run(
            thread_id=self.thread.id,
            agent_id=self.agent_id
        )
        messages_resp = self.project_client.agents.list_messages(thread_id=self.thread.id)
        # messages lenght
        #print(f"Messages length: {len(messages_resp.text_messages)}")
        # print all messages
        #for msg in messages_resp.text_messages:
        #    print(f"Message: {msg.text}")
        # Find and return the first assistant message (from oldest to newest)
        for msg in messages_resp.text_messages:
            return Response(chat_message=TextMessage(content=str(msg.text), source=self.agent_name))
        return Response(chat_message=TextMessage(content="No response from Foundry agent.", source=self.agent_name))

    async def on_reset(self, cancellation_token=None):
        #self.thread = self.project_client.agents.create_thread()
        pass

    @property
    def produced_message_types(self) -> Sequence[type[BaseChatMessage]]:
        return (TextMessage,)