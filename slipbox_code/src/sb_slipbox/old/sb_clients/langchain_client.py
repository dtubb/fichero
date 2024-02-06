# src/sb_slipbox/sb_clients/langchain_client.py

"""LangChain API client."""

from langchain import LLMPredictor, PromptTemplate

class LangchainClient:
    """Client for interacting with LangChain API."""
    
    def __init__(self, api_key):
        """Initialize with API key."""
        self.predictor = LLMPredictor(api_key)

    def summarize(self, text, instructions):
        """Generate a summary of the text."""
        prompt = PromptTemplate(
            template=instructions,
            input_variables=["text"],
            output_variables=["summary"]
        ).format(text=text)
        
        response = self.predictor.predict(
            prompt=prompt,
            max_tokens=100
        )

        return response["summary"]

    def generate_text(self, prompt):
        """Generate text for the given prompt."""
        response = self.predictor.predict(
            prompt=prompt, 
            max_tokens=512
        )

        return response["text"]