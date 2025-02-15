from ai.base_image_client import BaseImageClient
from typing import Optional
import asyncio

class ReCraftClient(BaseImageClient):
    def __init__(self, api_key: str):
        super().__init__(api_key)
        self.model = "recraft-ai/recraft-v3"
        self.model_params = {
            "prompt": "",  # Will be set during generation
            "size": "1365x1024",
            "style": "any"
        }
        self.max_prompt_length = 1000

    async def generate_image(self, prompt: str) -> Optional[bytes]:
        """
        Generate an image using the ReCraft model via Replicate API.
        """
        if len(prompt) > self.max_prompt_length:
            print(f"Warning: Truncating prompt from {len(prompt)} to {self.max_prompt_length} characters")
            prompt = prompt[:self.max_prompt_length]

        self.model_params["prompt"] = prompt
        
        try:
            loop = asyncio.get_event_loop()
            output = await loop.run_in_executor(
                None,
                lambda: self.client.run(
                    self.model,
                    input=self.model_params
                )
            )
            
            if output:
                # Handle file-like object directly
                image_data = await loop.run_in_executor(
                    None,
                    lambda: output.read()
                )
                return image_data
            return None
            
        except Exception as e:
            print(f"ReCraft generation error: {str(e)}")
            raise
