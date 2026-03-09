"""
vLLM Client Module
Handles communication with a vLLM server via the OpenAI-compatible API.
"""

import json
from typing import List, Dict, AsyncGenerator
import aiohttp
from openai import OpenAI, AsyncOpenAI

class VLLMClient:
    """Client for interacting with vLLM API using OpenAI compatibility layer."""

    SOCRATIC_SYSTEM_PROMPT = """You are a Socratic tutor helping a student defend their essay through critical questioning.

Your role:
- Ask probing questions to challenge assumptions and claims
- Request specific evidence and reasoning
- Highlight potential logical inconsistencies or gaps
- Guide the student to think deeper without giving direct answers
- Be respectful but intellectually rigorous
- Keep responses conversational and under 50 words
- Focus on one question or challenge at a time

Remember: Your goal is to strengthen their argument by making them defend it thoroughly."""

    def __init__(self, base_url: str = "http://localhost:8000/v1", model: str = "meta-llama/Meta-Llama-3.1-8B-Instruct"):
        """
        Initialize vLLM client.

        Args:
            base_url: vLLM OpenAI-compatible server URL
            model: Model name to use
        """
        self.base_url = base_url
        self.model = model
        self.client = OpenAI(base_url=base_url, api_key="EMPTY")
        self.async_client = AsyncOpenAI(base_url=base_url, api_key="EMPTY")

    def check_connection(self) -> bool:
        """
        Check if vLLM server is accessible.

        Returns:
            True if server is running, False otherwise
        """
        try:
            # Check models endpoint to verify connection
            self.client.models.list()
            return True
        except Exception as e:
            print(f"Connection check failed: {e}")
            return False

    def initialize_context(self, pdf_context: str) -> Dict:
        """
        Initialize conversation context with PDF content.

        Args:
            pdf_context: First 500 words from the student's essay

        Returns:
            Initial bot response welcoming the student
        """
        initial_prompt = f"""The student has submitted an essay. Here are the first 500 words:

---
{pdf_context}
---

Generate a brief welcoming message (under 40 words) that:
1. Acknowledges you've reviewed their essay
2. Asks them to explain their main thesis or central argument in their own words

Be encouraging but set an intellectually rigorous tone."""

        return self.generate(initial_prompt)

    def generate_socratic_response(
        self,
        student_input: str,
        pdf_context: str,
        conversation_history: List[Dict[str, str]]
    ) -> Dict:
        """
        Generate a Socratic response to student's statement.
        """
        # Format conversation history
        history_text = "\n".join([
            f"{msg['speaker'].upper()}: {msg['text']}"
            for msg in conversation_history[-6:]  # Last 6 exchanges for context
        ])

        prompt = f"""{self.SOCRATIC_SYSTEM_PROMPT}

Essay Context (first 500 words):
{pdf_context}

Recent Conversation:
{history_text if history_text else "(No prior conversation)"}

Student's latest statement:
"{student_input}"

Your Socratic response:"""

        return self.generate(prompt)

    async def generate_socratic_response_stream(
        self,
        student_input: str,
        pdf_context: str,
        conversation_history: List[Dict[str, str]]
    ) -> AsyncGenerator[str, None]:
        """
        Generate a Socratic response with streaming (word-by-word).
        """
        # Format conversation history
        history_text = "\n".join([
            f"{msg['speaker'].upper()}: {msg['text']}"
            for msg in conversation_history[-6:]  # Last 6 exchanges for context
        ])

        prompt = f"""{self.SOCRATIC_SYSTEM_PROMPT}

Essay Context (first 500 words):
{pdf_context}

Recent Conversation:
{history_text if history_text else "(No prior conversation)"}

Student's latest statement:
"{student_input}"

Your Socratic response:"""

        async for chunk in self.generate_stream(prompt):
            yield chunk

    async def generate_stream(self, prompt: str) -> AsyncGenerator[str, None]:
        """
        Generate response from vLLM with streaming.
        """
        try:
            stream = await self.async_client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                stream=True,
                temperature=0.7,
                top_p=0.9,
                max_tokens=150
            )
            async for chunk in stream:
                if chunk.choices[0].delta.content is not None:
                    yield chunk.choices[0].delta.content

        except Exception as e:
            yield f"[Error: {str(e)}]"

    def generate(self, prompt: str, stream: bool = False) -> Dict:
        """
        Generate response from vLLM.
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                stream=stream,
                temperature=0.7,
                top_p=0.9,
                max_tokens=150
            )

            if stream:
                # To fully support the old interface, though streaming is mostly done via the async generator
                return {"response": response, "stream": True}
            else:
                content = response.choices[0].message.content.strip()
                return {
                    "response": content,
                    "done": True
                }

        except Exception as e:
            return {
                "response": f"Error communicating with vLLM: {str(e)}",
                "error": True
            }

    def chat(self, messages: List[Dict[str, str]]) -> Dict:
        """
        Use chat endpoint for multi-turn conversations.
        """
        try:
            # Map roles properly
            formatted_messages = []
            for msg in messages:
                role = msg.get("role", "user")
                if role not in ["system", "user", "assistant"]:
                    role = "user"
                formatted_messages.append({
                    "role": role,
                    "content": msg.get("content", "")
                })

            response = self.client.chat.completions.create(
                model=self.model,
                messages=formatted_messages,
                temperature=0.7,
                top_p=0.9,
                max_tokens=150
            )

            content = response.choices[0].message.content.strip()
            return {
                "response": content,
                "done": True
            }

        except Exception as e:
            return {
                "response": f"Error: {str(e)}",
                "error": True
            }

if __name__ == "__main__":
    # Test the vLLM client
    client = VLLMClient()

    print("Checking vLLM connection...")
    if client.check_connection():
        print(f"✓ Connected to vLLM successfully (Model: {client.model})")

        sample_context = "The impact of social media on democratic discourse has been profound..."
        print("\nInitializing context with sample essay...")
        initial_response = client.initialize_context(sample_context.strip())
        print(f"Bot: {initial_response.get('response', 'No response')}")

        print("\nGenerating Socratic response...")
        student_statement = "I think social media algorithms are the main problem because they show people what they want to see."
        socratic_response = client.generate_socratic_response(
            student_input=student_statement,
            pdf_context=sample_context.strip(),
            conversation_history=[]
        )
        print(f"Bot: {socratic_response.get('response', 'No response')}")

    else:
        print("✗ Failed to connect to vLLM. Is it running?")
        print("  Try checking your vLLM server URL and making sure it's accessible.")
