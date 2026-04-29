from google import genai
from google.genai import types
from typing import List, Dict


class GoogleAIClient:
    def __init__(self, api_key: str):
        self.client = genai.Client(api_key=api_key)
        self.model = "gemini-3.1-flash-lite-preview"
        self.generation_config = types.GenerateContentConfig(
            temperature=0.7,
            max_output_tokens=2048,
        )

    async def generate_response(self,
                                system_prompt: str,
                                context: List[Dict],
                                message: str) -> str:
        try:
            content_parts: list[str] = []

            if system_prompt:
                content_parts.append(f"System Instructions: {system_prompt}\n")

            recent_context = context[-10:] if len(context) > 10 else context
            for ctx in recent_context:
                content_parts.append(f"User: {ctx['message']}\n")
                content_parts.append(f"Assistant: {ctx['response']}\n")

            content_parts.append(f"User: {message}\n")
            combined = "\n".join(content_parts)

            # google-genai SDK has a native async client — no run_in_executor needed
            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=combined,
                config=self.generation_config,
            )

            if response.text:
                return response.text
            return "I apologize, but I couldn't generate a response at this time."

        except Exception as e:
            print(f"Gemini API Error: {str(e)}")
            raise
