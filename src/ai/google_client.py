import google.generativeai as genai
from typing import List, Dict

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
            chat = self.model.start_chat()
            
            # Send system prompt first
            if system_prompt:
                chat.send_message(
                    f"Instructions: {system_prompt}",
                    generation_config=self.generation_config
                )

            # Use last 10 messages for context
            recent_context = context[-10:] if len(context) > 10 else context
            
            for ctx in recent_context:
                chat.send_message(
                    ctx["message"],
                    generation_config=self.generation_config
                )
                chat.send_message(
                    ctx["response"],
                    generation_config=self.generation_config
                )

            response = chat.send_message(
                message,
                generation_config=self.generation_config
            )
            
            if response.text:
                return response.text
            return "I apologize, but I couldn't generate a response at this time."
            
        except Exception as e:
            print(f"Gemini API Error: {str(e)}")
            raise
