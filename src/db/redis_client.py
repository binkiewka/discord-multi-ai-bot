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
        """Legacy method - kept for backwards compatibility"""
        return self.redis.get(f"allowed_channel:{server_id}")

    def set_allowed_channel(self, server_id: str, channel_id: str):
        """Legacy method - kept for backwards compatibility"""
        self.redis.set(f"allowed_channel:{server_id}", channel_id)

    # Multi-channel support methods
    def add_allowed_channel(self, server_id: str, channel_id: str):
        """Add a channel to the list of allowed channels"""
        key = f"allowed_channels:{server_id}"
        self.redis.sadd(key, channel_id)

    def remove_allowed_channel(self, server_id: str, channel_id: str):
        """Remove a channel from the list of allowed channels"""
        key = f"allowed_channels:{server_id}"
        self.redis.srem(key, channel_id)

    def get_allowed_channels(self, server_id: str) -> list[str]:
        """Get all allowed channels for a server"""
        key = f"allowed_channels:{server_id}"
        channels = self.redis.smembers(key)
        return list(channels) if channels else []

    def is_channel_allowed(self, server_id: str, channel_id: str) -> bool:
        """Check if a channel is allowed for a server"""
        key = f"allowed_channels:{server_id}"
        return self.redis.sismember(key, channel_id)

    def clear_allowed_channels(self, server_id: str):
        """Clear all allowed channels for a server"""
        key = f"allowed_channels:{server_id}"
        self.redis.delete(key)

    def migrate_single_to_multi_channel(self, server_id: str):
        """Migrate from single-channel to multi-channel format"""
        old_channel = self.get_allowed_channel(server_id)
        if old_channel:
            # Add the old channel to the new multi-channel set
            self.add_allowed_channel(server_id, old_channel)
            # Remove the old key
            self.redis.delete(f"allowed_channel:{server_id}")

    def get_server_model(self, server_id: str) -> str:
        """Legacy method - kept for backwards compatibility"""
        return self.redis.get(f"model:{server_id}") or "claude"

    def set_server_model(self, server_id: str, model: str):
        """Legacy method - kept for backwards compatibility"""
        self.redis.set(f"model:{server_id}", model)

    def get_server_role(self, server_id: str) -> str:
        """Legacy method - kept for backwards compatibility"""
        return self.redis.get(f"role:{server_id}") or "default"

    def set_server_role(self, server_id: str, role: str):
        """Legacy method - kept for backwards compatibility"""
        self.redis.set(f"role:{server_id}", role)

    # Channel-specific role and model methods
    def get_default_model(self, server_id: str) -> str:
        """Get server-wide default model"""
        return self.redis.get(f"default_model:{server_id}") or "claude"

    def set_default_model(self, server_id: str, model: str):
        """Set server-wide default model"""
        self.redis.set(f"default_model:{server_id}", model)

    def get_default_role(self, server_id: str) -> str:
        """Get server-wide default role"""
        return self.redis.get(f"default_role:{server_id}") or "default"

    def set_default_role(self, server_id: str, role: str):
        """Set server-wide default role"""
        self.redis.set(f"default_role:{server_id}", role)

    def get_channel_model(self, server_id: str, channel_id: str) -> str:
        """Get channel-specific model, falls back to default"""
        channel_model = self.redis.get(f"channel_model:{server_id}:{channel_id}")
        if channel_model:
            return channel_model
        return self.get_default_model(server_id)

    def set_channel_model(self, server_id: str, channel_id: str, model: str):
        """Set channel-specific model"""
        self.redis.set(f"channel_model:{server_id}:{channel_id}", model)

    def get_channel_role(self, server_id: str, channel_id: str) -> str:
        """Get channel-specific role, falls back to default"""
        channel_role = self.redis.get(f"channel_role:{server_id}:{channel_id}")
        if channel_role:
            return channel_role
        return self.get_default_role(server_id)

    def set_channel_role(self, server_id: str, channel_id: str, role: str):
        """Set channel-specific role"""
        self.redis.set(f"channel_role:{server_id}:{channel_id}", role)

    def get_all_channel_settings(self, server_id: str) -> dict:
        """Get all channel-specific settings for a server"""
        allowed_channels = self.get_allowed_channels(server_id)
        settings = {}

        for channel_id in allowed_channels:
            settings[channel_id] = {
                'role': self.get_channel_role(server_id, channel_id),
                'model': self.get_channel_model(server_id, channel_id)
            }

        return settings

    def migrate_server_to_channel_settings(self, server_id: str):
        """Migrate from server-wide to channel-specific settings"""
        # Get old server-wide settings
        old_model = self.get_server_model(server_id)
        old_role = self.get_server_role(server_id)

        # Set as server defaults
        self.set_default_model(server_id, old_model)
        self.set_default_role(server_id, old_role)

        # Apply to all allowed channels
        allowed_channels = self.get_allowed_channels(server_id)
        for channel_id in allowed_channels:
            self.set_channel_model(server_id, channel_id, old_model)
            self.set_channel_role(server_id, channel_id, old_role)

        # Remove old keys
        self.redis.delete(f"model:{server_id}")
        self.redis.delete(f"role:{server_id}")
