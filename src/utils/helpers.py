from typing import Optional
import discord

async def send_chunked_message(channel: discord.TextChannel, message: str, reference: Optional[discord.Message] = None):
    """
    Sends a message in chunks if it exceeds Discord's character limit
    """
    max_length = 2000
    
    if len(message) <= max_length:
        return await channel.send(message, reference=reference)
    
    chunks = []
    current_chunk = ""
    
    for line in message.split('\n'):
        if len(current_chunk) + len(line) + 1 <= max_length:
            current_chunk += line + '\n'
        else:
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = line + '\n'
    
    if current_chunk:
        chunks.append(current_chunk)
    
    # Send first chunk with reference
    if chunks:
        await channel.send(chunks[0], reference=reference)
        
    # Send remaining chunks
    for chunk in chunks[1:]:
        await channel.send(chunk)
