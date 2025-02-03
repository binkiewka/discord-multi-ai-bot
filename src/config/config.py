import os
from dataclasses import dataclass
import yaml

@dataclass
class Role:
    name: str
    description: str
    system_prompt: str

class Config:
    def __init__(self):
        self.discord_token = os.getenv('DISCORD_TOKEN')
        self.anthropic_api_key = os.getenv('ANTHROPIC_API_KEY')
        self.openai_api_key = os.getenv('OPENAI_API_KEY')
        self.google_api_key = os.getenv('GOOGLE_API_KEY')
        self.replicate_api_token = os.getenv('REPLICATE_API_TOKEN')
        self.redis_host = os.getenv('REDIS_HOST', 'localhost')
        self.redis_port = int(os.getenv('REDIS_PORT', 6379))
        self.owner_id = os.getenv('OWNER_ID')
        self.roles = self._load_roles()

        # Validate required environment variables
        if not all([
            self.discord_token,
            self.anthropic_api_key,
            self.openai_api_key,
            self.google_api_key,
            self.replicate_api_token,
            self.owner_id
        ]):
            raise ValueError("Missing required environment variables")

    def _load_roles(self) -> dict[str, Role]:
        try:
            with open('src/config/roles.yaml', 'r', encoding='utf-8') as f:
                content = f.read()
                print("YAML Content:")
                print(content)  # Debug print
                roles_data = yaml.safe_load(content)
                
                if not roles_data:
                    print("Empty YAML file")
                    return {}

                roles = {}
                for role_id, data in roles_data.items():
                    roles[role_id] = Role(
                        name=data.get('name', 'Unknown'),
                        description=data.get('description', ''),
                        system_prompt=data.get('system_prompt', '')
                    )
                return roles
        except yaml.YAMLError as e:
            print(f"YAML parsing error: {str(e)}")
            raise
        except Exception as e:
            print(f"Error loading roles: {str(e)}")
            raise ValueError(f"Failed to load roles: {str(e)}")
