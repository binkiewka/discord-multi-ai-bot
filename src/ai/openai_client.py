from openai import AsyncOpenAI
from typing import List, Dict


class OpenAIClient:
    def __init__(self, api_key: str):
        self.client = AsyncOpenAI(api_key=api_key)

    async def generate_response(self,
                                system_prompt: str,
                                context: List[Dict],
                                message: str) -> str:
        try:
            messages = []

            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})

            recent_context = context[-10:] if len(context) > 10 else context
            for ctx in recent_context:
                messages.append({"role": "user", "content": ctx["message"]})
                messages.append({"role": "assistant", "content": ctx["response"]})

            messages.append({"role": "user", "content": message})

            response = await self.client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=messages,
                max_tokens=2048,
                temperature=0.7,
                presence_penalty=0.6,
                frequency_penalty=0.5,
            )

            return response.choices[0].message.content

        except Exception as e:
            print(f"OpenAI API Error: {str(e)}")
            raise
