import json
from typing import Optional
import redis

class RedisClient:
    def __init__(self, host: str, port: int):
        self.redis = redis.Redis(host=host, port=port, decode_responses=True)
        self.max_context_messages = 30  # Store 30 messages per channel
        self.context_expiry = 7200      # 2 hours expiry

    def get_context(self, server_id: str, channel_id: str) -> list[dict]:
        key = f"context:{server_id}:{channel_id}"
        context = self.redis.get(key)
        return json.loads(context) if context else []

    def add_to_context(self, server_id: str, channel_id: str, 
                      user_id: str, message: str, response: str):
        key = f"context:{server_id}:{channel_id}"
        context = self.get_context(server_id, channel_id)
        
        context.append({
            "user_id": user_id,
            "message": message,
            "response": response
        })
        
        # Keep only last 30 messages for context
        if len(context) > self.max_context_messages:
            context = context[-self.max_context_messages:]
            
        self.redis.set(key, json.dumps(context))
        self.redis.expire(key, self.context_expiry)  # Expire after 2 hours

    def get_allowed_channel(self, server_id: str) -> Optional[str]:
        return self.redis.get(f"allowed_channel:{server_id}")

    def set_allowed_channel(self, server_id: str, channel_id: str):
        self.redis.set(f"allowed_channel:{server_id}", channel_id)

    def get_server_model(self, server_id: str) -> str:
        return self.redis.get(f"model:{server_id}") or "claude"

    def set_server_model(self, server_id: str, model: str):
        self.redis.set(f"model:{server_id}", model)

    def get_server_role(self, server_id: str) -> str:
        return self.redis.get(f"role:{server_id}") or "default"

    def set_server_role(self, server_id: str, role: str):
        self.redis.set(f"role:{server_id}", role)
