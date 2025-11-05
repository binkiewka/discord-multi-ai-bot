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
        return self.redis.get(f"model:{server_id}") or "claude"

    def set_server_model(self, server_id: str, model: str):
        self.redis.set(f"model:{server_id}", model)

    def get_server_role(self, server_id: str) -> str:
        return self.redis.get(f"role:{server_id}") or "default"

    def set_server_role(self, server_id: str, role: str):
        self.redis.set(f"role:{server_id}", role)

    # Alias methods for server-wide defaults (same as server-wide methods above)
    def get_default_model(self, server_id: str) -> str:
        """Get server-wide default model (alias for get_server_model)"""
        return self.get_server_model(server_id)

    def set_default_model(self, server_id: str, model: str):
        """Set server-wide default model (alias for set_server_model)"""
        self.set_server_model(server_id, model)

    def get_default_role(self, server_id: str) -> str:
        """Get server-wide default role (alias for get_server_role)"""
        return self.get_server_role(server_id)

    def set_default_role(self, server_id: str, role: str):
        """Set server-wide default role (alias for set_server_role)"""
        self.set_server_role(server_id, role)

    # Channel-specific role methods
    def get_channel_role(self, server_id: str, channel_id: str) -> str:
        """Get role for specific channel with fallback chain:
        1. Channel-specific role
        2. Server-wide role
        3. Default role
        """
        # Try channel-specific first
        channel_role = self.redis.get(f"channel_role:{server_id}:{channel_id}")
        if channel_role:
            return channel_role

        # Fall back to server-wide
        server_role = self.redis.get(f"role:{server_id}")
        if server_role:
            return server_role

        # Fall back to default
        return "default"

    def set_channel_role(self, server_id: str, channel_id: str, role: str):
        """Set role for specific channel"""
        self.redis.set(f"channel_role:{server_id}:{channel_id}", role)

    def clear_channel_role(self, server_id: str, channel_id: str):
        """Remove channel-specific role (falls back to server-wide)"""
        self.redis.delete(f"channel_role:{server_id}:{channel_id}")

    def get_all_channel_roles(self, server_id: str) -> dict[str, str]:
        """Get all channel→role mappings for server"""
        pattern = f"channel_role:{server_id}:*"
        keys = self.redis.keys(pattern)
        result = {}
        for key in keys:
            # Extract channel_id from key
            channel_id = key.split(":")[-1]
            role = self.redis.get(key)
            if role:
                result[channel_id] = role
        return result

    # Channel-specific model methods
    def get_channel_model(self, server_id: str, channel_id: str) -> str:
        """Get model for specific channel with fallback chain:
        1. Channel-specific model
        2. Server-wide model
        3. Default model (claude)
        """
        # Try channel-specific first
        channel_model = self.redis.get(f"channel_model:{server_id}:{channel_id}")
        if channel_model:
            return channel_model

        # Fall back to server-wide
        server_model = self.redis.get(f"model:{server_id}")
        if server_model:
            return server_model

        # Fall back to default
        return "claude"

    def set_channel_model(self, server_id: str, channel_id: str, model: str):
        """Set model for specific channel"""
        self.redis.set(f"channel_model:{server_id}:{channel_id}", model)

    def clear_channel_model(self, server_id: str, channel_id: str):
        """Remove channel-specific model (falls back to server-wide)"""
        self.redis.delete(f"channel_model:{server_id}:{channel_id}")

    def get_all_channel_models(self, server_id: str) -> dict[str, str]:
        """Get all channel→model mappings for server"""
        pattern = f"channel_model:{server_id}:*"
        keys = self.redis.keys(pattern)
        result = {}
        for key in keys:
            # Extract channel_id from key
            channel_id = key.split(":")[-1]
            model = self.redis.get(key)
            if model:
                result[channel_id] = model
        return result
