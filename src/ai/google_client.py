import google.generativeai as genai
from typing import List, Dict
import asyncio
from functools import partial

class GoogleAIClient:
    def __init__(self, api_key: str):
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-1.5-pro')
        self.generation_config = genai.types.GenerationConfig(
            temperature=0.7,
            top_p=0.9,
            top_k=40,
            max_output_tokens=2048,
        )

    async def generate_response(self, 
                              system_prompt: str, 
                              context: List[Dict], 
                              message: str) -> str:
        try:
            # Prepare all messages in a single content string
            content = []
            
            # Add system prompt if present
            if system_prompt:
                content.append(f"System Instructions: {system_prompt}\n")

            # Use last 10 messages for context
            recent_context = context[-10:] if len(context) > 10 else context
            
            # Add context messages in a more efficient format
            for ctx in recent_context:
                content.append(f"User: {ctx['message']}\n")
                content.append(f"Assistant: {ctx['response']}\n")

            # Add current message
            content.append(f"User: {message}\n")
            
            # Create a combined content string
            combined_content = "\n".join(content)
            
            # Run the synchronous generate_content in the default thread pool
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                partial(self.model.generate_content, combined_content, generation_config=self.generation_config)
            )
            
            if response.text:
                return response.text
            return "I apologize, but I couldn't generate a response at this time."
            
        except Exception as e:
            print(f"Gemini API Error: {str(e)}")
            raise
