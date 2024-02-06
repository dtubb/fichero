# src/sb_slipbox/sb_clients/chatgpt_client.py

"""ChatGPT API client."""

import openai

class ChatGPTClient:
    """Client for interacting with ChatGPT API."""

    def __init__(self, api_key):
        """Initialize with API key."""
        openai.api_key = api_key

    def ask(self, prompt):
        """Send question and get response from ChatGPT."""
        response = openai.Completion.create(
            engine="text-davinci-003", 
            prompt=prompt,
            max_tokens=1024,
            n=1,
            stop=None,
            temperature=0.5,
        ).choices[0].text
        return response

    def converse(self, chat_history):
        """Continue an ongoing conversation with ChatGPT."""
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo", 
            messages=chat_history
        )
        return response.choices[0].message