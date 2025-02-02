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
            
            # Add system prompt
            if system_prompt:
                messages.append({
                    "role": "system",
                    "content": system_prompt
                })

            # Add recent context (last 10 messages for more context than other models)
            recent_context = context[-10:] if len(context) > 10 else context
            
            for ctx in recent_context:
                messages.append({
                    "role": "user",
                    "content": ctx["message"]
                })
                messages.append({
                    "role": "assistant",
                    "content": ctx["response"]
                })

            # Add current message
            messages.append({
                "role": "user",
                "content": message
            })

            response = await self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=messages,
                max_tokens=2048,
                temperature=0.7,
                top_p=0.9,
                presence_penalty=0.6,  # Encourages more varied responses
                frequency_penalty=0.5,  # Reduces repetition
                response_format={"type": "text"}  # Ensures text response
            )

            return response.choices[0].message.content

        except Exception as e:
            print(f"OpenAI API Error: {str(e)}")
            raise
