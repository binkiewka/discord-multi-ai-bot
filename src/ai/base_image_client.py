from typing import List, Dict, Optional, Any
import replicate
import asyncio
import json

class BaseImageClient:
    def __init__(self, api_key: str):
        self.client = replicate
        self.client.api_token = api_key
        self.model = None
        self.model_params = {}

    def _debug_print(self, message: str, data: Any = None):
        """Helper method for consistent debug printing"""
        print(f"[BaseImageClient] {message}")
        if data is not None:
            print(f"[BaseImageClient] Data: {json.dumps(data, indent=2) if isinstance(data, (dict, list)) else data}")

    async def generate_image(self, prompt: str) -> Optional[bytes]:
        """Base method for image generation"""
        if not self.model:
            raise ValueError("Model must be set by child class")

        try:
            self._debug_print(f"Starting generation with model: {self.model}")
            self._debug_print("Using client type:", type(self.client))
            
            loop = asyncio.get_event_loop()
            
            # Attempt to run the model and capture full response
            response = await loop.run_in_executor(
                None,
                lambda: self.client.run(
                    self.model,
                    input=self.model_params
                )
            )
            
            self._debug_print("Raw API response:", response)
            return response
            
        except Exception as e:
            self._debug_print(f"Base client error: {str(e)}")
            self._debug_print(f"Error type: {type(e)}")
            if hasattr(e, '__dict__'):
                self._debug_print("Error attributes:", e.__dict__)
            raise

    async def generate_response(self, 
                              system_prompt: str, 
                              context: List[Dict], 
                              message: str) -> str:
        """Generate a response for the image generation."""
        try:
            self._debug_print("Starting response generation")
            image_data = await self.generate_image(message)
            
            if image_data:
                self._debug_print("Image generation successful")
                return "Image generated successfully!"
            
            self._debug_print("No image data received")
            return "I apologize, but I couldn't generate an image at this time."
            
        except Exception as e:
            self._debug_print(f"Response generation error: {str(e)}")
            return f"I apologize, but there was an error generating the image: {str(e)}"
