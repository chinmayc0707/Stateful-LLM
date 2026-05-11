import os
import asyncio
import selectors

# FIX: Set the Windows event loop policy globally at the module level.
# This must happen before ANY other asyncio-related libraries are initialized.
if os.name == 'nt':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import selectors
from typing import Annotated, List, Dict, Any, Optional, Callable
from pathlib import Path
from functools import wraps

from rich.console import Console
from rich.markdown import Markdown
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
import tiktoken
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from dotenv import load_dotenv

# Load environment variables
env_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=env_path)

# Define the state of our graph
class State(dict):
    messages: Annotated[list[BaseMessage], add_messages]

def rich_text(func: Callable):
    """Decorator to render the returned text of a function as Markdown using Rich."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        console = Console()
        console.print("\n[bold blue]Assistant:[/bold blue]")
        console.print(Markdown(result))
        console.print("\n" + "-"*40 + "\n")
        return result
    return wrapper

def stream(func: Callable):
    """Decorator to convert the async stream into a synchronous generator."""
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        # We use the manager's existing loop to run the async generator
        # Since we can't simply 'yield' from an async function in a sync one,
        # we use a helper to run the async generator to completion.
        
        async def gen_wrapper():
            async for chunk in func(self, *args, **kwargs):
                yield chunk

        # This is the trick: we use a synchronous queue or a simple list 
        # but for a true 'stream' feel in sync, we use a custom generator
        import queue
        q = queue.Queue()
        
        def producer():
            # Run the async generator in a separate thread or just run_until_complete
            # for each chunk. For simplicity in this manager, we'll use a loop.
            loop = self._loop
            
            async def run_and_push():
                async for chunk in func(self, *args, **kwargs):
                    q.put(chunk)
                q.put(None) # Sentinel
            
            loop.run_until_complete(run_and_push())

        import threading
        threading.Thread(target=producer, daemon=True).start()

        while True:
            item = q.get()
            if item is None:
                break
            yield item
            
    return wrapper

class LangGraphManager:
    def __init__(self, db_url: Optional[str] = None):
        self.db_url = db_url or os.getenv("DATABASE_URL")
        if not self.db_url:
            raise ValueError("DATABASE_URL must be provided or set in .env file")
        
        self.llm = ChatOpenAI(
        model="google/gemma-4-31b-it:free",
        openai_api_base="https://openrouter.ai/api/v1",
        openai_api_key=os.getenv("OPENROUTER_API_KEY")
        )
        self.checkpointer = None
        self.app = None
        
        # Use a simple loop retrieval. 
        # The global policy is now handled at the module level.
        try:
            self._loop = asyncio.get_event_loop()
        except RuntimeError:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

    async def _initialize(self):
        """Internal async method to initialize the checkpointer and compile the graph."""
        if self.app is None:
            # from_conn_string is an async context manager. 
            # We must enter it to get the actual saver instance.
            # Since the manager needs to keep the saver alive, we'll use a manual enter.
            self.checkpointer_ctx = AsyncPostgresSaver.from_conn_string(self.db_url)
            self.checkpointer = await self.checkpointer_ctx.__aenter__()
            await self.checkpointer.setup()

            workflow = StateGraph(State)
            
            async def call_model(state: State):
                response = await self.llm.ainvoke(state["messages"])
                return {"messages": [response]}

            async def summarize_conversation(state: State):
                """Summarizes the conversation based on actual token usage (75% threshold)."""
                messages = state["messages"]
                
                # 1. Calculate total tokens in current history
                # Using cl100k_base as a reliable proxy for token counting
                encoding = tiktoken.get_encoding("cl100k_base")
                full_text = " ".join([m.content for m in messages if hasattr(m, 'content')])
                token_count = len(encoding.encode(full_text))
                
                # 2. Define Context Limit (Gemma-4-31B has a huge window, but we set a practical limit)
                # 128,000 tokens is common; 75% is 96,000.
                CONTEXT_LIMIT = 128000 
                THRESHOLD = 0.75 * CONTEXT_LIMIT

                if token_count > THRESHOLD:
                    # 3. Intelligent Summarization Prompt
                    summary_prompt = (
                        "The conversation has reached its context limit. Please summarize the history "
                        "below. IMPORTANT: You MUST preserve all key identities (names), critical facts, "
                        "decisions made, and the overall intent of the user. Keep the summary concise "
                        "but comprehensive enough that the agent doesn't lose the 'who' and 'what' "
                        "of the conversation.\n\n"
                        f"CONVERSATION HISTORY:\n{messages}"
                    )
                    
                    summary_response = await self.llm.ainvoke([HumanMessage(content=summary_prompt)])
                    
                    # Return the summary as a system-like message to guide future turns
                    summary_msg = AIMessage(
                        content=f"SYSTEM MEMORY SUMMARY: {summary_response.content}"
                    )
                    
                    # To effectively prune history in LangGraph's add_messages, 
                    # we would typically return a state update that replaces messages.
                    # For this implementation, we provide the summary to the agent.
                    return {"messages": [summary_msg]}
                
                return {"messages": []}

            workflow.add_node("agent", call_model)
            workflow.add_node("summarize", summarize_conversation)
            
            # Flow: Start -> Summarize (if needed) -> Agent -> End
            workflow.add_edge(START, "summarize")
            workflow.add_edge("summarize", "agent")
            workflow.add_edge("agent", END)

            self.app = workflow.compile(checkpointer=self.checkpointer)

    async def _async_chat(self, prompt: str, thread_id: str) -> str:
        """Core async chat logic."""
        await self._initialize()
        config = {"configurable": {"thread_id": thread_id}}
        input_data = {"messages": [HumanMessage(content=prompt)]}
        result = await self.app.ainvoke(input_data, config=config)
        return result["messages"][-1].content

    async def _async_chat_stream(self, prompt: str, thread_id: str):
        """Core async streaming logic using astream."""
        await self._initialize()
        config = {"configurable": {"thread_id": thread_id}}
        input_data = {"messages": [HumanMessage(content=prompt)]}
        
        async for event in self.app.astream(input_data, config=config, stream_mode="messages"):
            # event is a tuple of (message, metadata) in newer langgraph
            # or just the message.
            msg, metadata = event
            if msg.content:
                yield msg.content

    async def _async_view_conversation(self, thread_id: str) -> List[Dict[str, str]]:
        """Core async history logic."""
        await self._initialize()
        config = {"configurable": {"thread_id": thread_id}}
        state = await self.app.get_state(config)
        
        if not state or "messages" not in state.values:
            return []

        history = []
        for msg in state.values["messages"]:
            role = "User" if isinstance(msg, HumanMessage) else "Assistant"
            history.append({"role": role, "content": msg.content})
        return history

    @rich_text
    @rich_text
    def chat(self, prompt: str, thread_id: str) -> str:
        """
        Synchronous wrapper for the chat method.
        No 'await' needed when calling this.
        """
        return self._loop.run_until_complete(self._async_chat(prompt, thread_id))

    @stream
    def stream_chat(self, prompt: str, thread_id: str):
        """
        Synchronous generator that streams the chat response.
        """
        return self._async_chat_stream(prompt, thread_id)

    def view_conversation(self, thread_id: str) -> List[Dict[str, str]]:
        """
        Synchronous wrapper for the view_conversation method.
        No 'await' needed when calling this.
        """
        return self._loop.run_until_complete(self._async_view_conversation(thread_id))

    def delete_thread(self, thread_id: str) -> bool:
        """
        Deletes all checkpoints and state for a specific thread_id.
        """
        return self._loop.run_until_complete(self._async_delete_thread(thread_id))

    async def _async_delete_thread(self, thread_id: str) -> bool:
        """Core async logic to delete thread data from the database."""
        from psycopg import AsyncConnection
        
        try:
            # Create a temporary connection to the DB to perform the cleanup
            async with await AsyncConnection.connect(self.db_url) as conn:
                async with conn.cursor() as cur:
                    # LangGraph stores checkpoints in 'checkpoints' and 'checkpoint_blobs'
                    # We remove all entries associated with this thread_id
                    await cur.execute(
                        "DELETE FROM checkpoints WHERE thread_id = %s", 
                        (thread_id,)
                    )
                    await cur.execute(
                        "DELETE FROM checkpoint_blobs WHERE thread_id = %s", 
                        (thread_id,)
                    )
                    await conn.commit()
            return True
        except Exception as e:
            print(f"Error deleting thread {thread_id}: {e}")
            return False

# --- Example Usage ---
if __name__ == "__main__":
    
    llm=LangGraphManager(os.getenv('DATABASE_URL'))
    try:
        # # Using a fixed prompt for automated debugging
        # prompt=input("Enter prompt: ")
        # # print(f"Prompt: {prompt}")
        # # llm.chat(prompt,'debug_thread1')
        # llm.stream_chat(prompt,'debug_thread1')

        llm.delete_thread('debug_thread1')
        
    except Exception as e:
        print(f"An error occurred: {e}")
