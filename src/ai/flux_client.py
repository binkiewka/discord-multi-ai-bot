from ai.base_image_client import BaseImageClient
from typing import Optional
import asyncio

class FluxClient(BaseImageClient):
    def __init__(self, api_key: str):
        super().__init__(api_key)
        self.model = "black-forest-labs/flux-schnell"

    async def generate_image(self, prompt: str) -> Optional[bytes]:
        """
        Generate an image using the Flux model via Replicate API.
        """
        try:
            loop = asyncio.get_event_loop()
            output = await loop.run_in_executor(
                None,
                lambda: self.client.run(
                    self.model,
                    input={
                        "prompt": prompt,
                        "go_fast": True,
                        "num_outputs": 1,
                        "aspect_ratio": "4:3",
                        "output_format": "png",
                        "output_quality": 100,
                        "negative_prompt": "bad quality, bad anatomy, bad hands, bad fingers, six fingers, mutated hands, poorly drawn hands, poorly drawn face, mutation, deformed, extra limbs, extra fingers, disfigured, bad proportions, gross proportions, blurry, duplicate, extra arms, extra legs, fused fingers, too many fingers, unclear eyes, poorly drawn eyes, imperfect eyes"
                    }
                )
            )

            if isinstance(output, list) and len(output) > 0:
                # Get the first output item and read it directly
                image_data = await loop.run_in_executor(
                    None,
                    lambda: output[0].read()
                )
                return image_data
            return None

        except Exception as e:
            print(f"Flux generation error: {str(e)}")
            raise
