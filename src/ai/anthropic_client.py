from anthropic import AsyncAnthropic
from typing import List, Dict

class AnthropicClient:
    def __init__(self, api_key: str):
        self.client = AsyncAnthropic(api_key=api_key)

    async def generate_response(self, 
                              system_prompt: str, 
                              context: List[Dict], 
                              message: str) -> str:
        try:
            # Use last 10 messages for context
            recent_context = context[-10:] if len(context) > 10 else context
            
            messages = []
            for ctx in recent_context:
                messages.append({
                    "role": "user",
                    "content": ctx["message"]
                })
                messages.append({
                    "role": "assistant",
                    "content": ctx["response"]
                })

            messages.append({
                "role": "user",
                "content": message
            })

            response = await self.client.messages.create(
                model="claude-haiku-4-5",
                system=system_prompt,
                messages=messages,
                max_tokens=2048,
                temperature=0.7,
                top_p=0.9
            )

            return response.content[0].text
        except Exception as e:
            print(f"Claude API Error: {str(e)}")
            raise
