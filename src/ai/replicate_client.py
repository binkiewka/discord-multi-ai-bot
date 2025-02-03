import os 
import replicate
from typing import List, Dict, Optional
import asyncio
import aiohttp
import time

class ReplicateClient:
    def __init__(self, api_key: str):
        self.client = replicate
        self.client.api_token = api_key
        self.model = "black-forest-labs/flux-schnell"

    async def generate_image(self, prompt: str) -> Optional[str]:
        """
        Generate an image using the Flux-schnell model via Replicate API
        
        Args:
            prompt (str): The text prompt to generate the image from
            
        Returns:
            Optional[str]: URL of the generated image or None if generation failed
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
                        "output_quality": 100
                    }
                )
            )

            if output and isinstance(output, list) and len(output) > 0:
                # Wait briefly for the image to be available
                await asyncio.sleep(2)
                return output[0]
            return None

        except Exception as e:
            print(f"Replicate API Error: {str(e)}")
            raise

    async def download_image(self, url: str, max_retries: int = 3) -> Optional[bytes]:
        """
        Download the generated image from the provided URL with retry logic
        
        Args:
            url (str): URL of the image to download
            max_retries (int): Maximum number of download attempts
            
        Returns:
            Optional[bytes]: Image data as bytes or None if download failed
        """
        timeout = aiohttp.ClientTimeout(total=30)  # 30 seconds total timeout
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

        for attempt in range(max_retries):
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url, headers=headers) as response:
                        if response.status == 200:
                            return await response.read()
                        elif response.status == 404:
                            # If image is not ready, wait and retry
                            await asyncio.sleep(2 * (attempt + 1))
                            continue
                        else:
                            print(f"Download failed with status {response.status}, response: {await response.text()}")
                            
            except asyncio.TimeoutError:
                print(f"Download timeout on attempt {attempt + 1}")
                await asyncio.sleep(2 * (attempt + 1))
                continue
            except Exception as e:
                print(f"Download error on attempt {attempt + 1}: {str(e)}")
                await asyncio.sleep(2 * (attempt + 1))
                continue
                
        print(f"All download attempts failed for URL: {url}")
        return None

    async def generate_response(self, 
                              system_prompt: str, 
                              context: List[Dict], 
                              message: str) -> str:
        """
        Generate a response containing an image URL based on the text prompt
        
        Args:
            system_prompt (str): System prompt (ignored for image generation)
            context (List[Dict]): Conversation context (ignored for image generation)
            message (str): The text prompt to generate the image from
            
        Returns:
            str: A message containing the image URL or an error message
        """
        try:
            image_url = await self.generate_image(message)
            if not image_url:
                return "I apologize, but I couldn't generate an image at this time."

            # Add a small delay before attempting to download
            await asyncio.sleep(2)
            
            # Attempt to download with retries
            image_data = await self.download_image(image_url)
            if not image_data:
                return f"I generated an image, but couldn't download it. You can try viewing it directly at: {image_url}"

            return f"I've generated an image based on your prompt. You can view it here: {image_url}"
            
        except Exception as e:
            print(f"Image generation error: {str(e)}")
            return f"I apologize, but there was an error generating the image: {str(e)}"
