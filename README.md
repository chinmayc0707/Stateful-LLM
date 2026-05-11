# LangGraph Manager

A Python application using LangGraph, Langchain, and psycopg3 for PostgreSQL-based state management and asynchronous checkpointing. This application provides an easy-to-use manager for running stateful AI agent workflows.

## Features

- **OpenRouter LLM Integration**: Uses the `google/gemma-4-31b-it:free` model by default via Langchain.
- **PostgreSQL Checkpointing**: Utilizes `AsyncPostgresSaver` for persisting the state and memory of agent threads.
- **Smart Context Summarization**: Automatically summarizes conversation history to prune tokens if the context exceeds 75% of a 128,000 token limit.
- **Synchronous Wrappers**: Provides easy-to-use decorators (`@rich_text`, `@stream`) allowing you to use async agent workflows in a synchronous context, including streaming responses and rich Markdown terminal output.

## Installation

1. Create a virtual environment and activate it (e.g. `python3 -m venv venv` and `source venv/bin/activate`).
2. Install the required dependencies:
   ```bash
   pip install langgraph langgraph-checkpoint-postgres langchain-openai python-dotenv psycopg[binary] rich tiktoken
   ```

## Configuration

You must create a `.env` file in the same directory as the script with the following variables:

```env
DATABASE_URL=postgresql://user:password@localhost:5432/yourdatabase
OPENROUTER_API_KEY=your_openrouter_api_key
```

## Example Usage

Here is a quick example of how to use the `LangGraphManager`:

```python
import os
from langgraph_manager import LangGraphManager

if __name__ == "__main__":
    llm = LangGraphManager(os.getenv('DATABASE_URL'))

    try:
        # Prompt the user for input
        prompt = input("Enter prompt: ")

        # Stream the chat response to the console
        for chunk in llm.stream_chat(prompt, 'debug_thread1'):
            print(chunk, end='')

        # Optional: Delete the thread history when done
        # print(llm.delete_thread('debug_thread1'))

    except Exception as e:
        print(f"An error occurred: {e}")
```
