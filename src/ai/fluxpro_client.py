from ai.base_image_client import BaseImageClient
from typing import Optional
import asyncio


class FluxProClient(BaseImageClient):
    def __init__(self, api_key: str):
        super().__init__(api_key)
        self.model = "black-forest-labs/flux-1.1-pro"
        self.model_params = {
            "prompt": "",
            "aspect_ratio": "4:3",
            "output_format": "png",
            "output_quality": 100,
            "prompt_upsampling": True,
        }

    async def generate_image(self, prompt: str) -> Optional[bytes]:
        self.model_params["prompt"] = prompt

        try:
            loop = asyncio.get_running_loop()
            output = await loop.run_in_executor(
                None,
                lambda: self.client.run(self.model, input=self.model_params),
            )

            if output:
                image_data = await loop.run_in_executor(None, lambda: output.read())
                return image_data
            return None

        except Exception as e:
            print(f"FluxPro generation error: {str(e)}")
            raise
