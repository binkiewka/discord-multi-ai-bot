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
        print(f"[BaseImageClient] {message}")
        if data is not None:
            print(
                f"[BaseImageClient] Data: "
                f"{json.dumps(data, indent=2) if isinstance(data, (dict, list)) else data}"
            )

    async def generate_image(self, prompt: str) -> Optional[bytes]:
        if not self.model:
            raise ValueError("Model must be set by child class")

        try:
            self._debug_print(f"Starting generation with model: {self.model}")

            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.run(self.model, input=self.model_params),
            )

            self._debug_print("Raw API response:", response)
            return response

        except Exception as e:
            self._debug_print(f"Base client error: {str(e)}")
            if hasattr(e, "__dict__"):
                self._debug_print("Error attributes:", e.__dict__)
            raise

    async def generate_response(self,
                                system_prompt: str,
                                context: List[Dict],
                                message: str) -> str:
        try:
            image_data = await self.generate_image(message)
            if image_data:
                return "Image generated successfully!"
            return "I apologize, but I couldn't generate an image at this time."
        except Exception as e:
            return f"I apologize, but there was an error generating the image: {str(e)}"
