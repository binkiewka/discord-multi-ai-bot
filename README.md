# Discord Multi-AI Bot

A versatile Discord bot that leverages multiple AI providers (Anthropic Claude, OpenAI GPT-4, and Google Gemini) with advanced context memory and role-based interactions.

## Features

### AI Integration
- **Multiple AI Providers**
  - Anthropic Claude (claude-3-opus-20240229)
  - OpenAI GPT-4 (gpt-4-turbo-preview)
  - Google Gemini (gemini-pro)
- **Seamless Model Switching** - Switch between AI models per server
- **Context Memory** - Maintains conversation history using Redis
- **Multi-User Support** - Multiple users can participate in the same conversation thread

### Role-Based System
- Predefined roles with unique personalities and behaviors
- Easy to add new roles via YAML configuration
- Includes roles like:
  - Default Assistant
  - Concise Mode
  - Creative Assistant
  - Academic Expert
  - Comedian
  - Poet
  - Rapper
  - Prompt Generator
  - Dream Interpreter
  - Domain Name Generator
  - DIY Expert

### Server Management
- **Channel-Specific Responses** - Bot only responds in designated channels
- **Per-Server Configuration** - Each server maintains its own settings
- **Admin Controls** - Server administrators can manage bot settings

## Setup

### Prerequisites
- Docker and Docker Compose
- Discord Bot Token
- AI Provider API Keys (Anthropic, OpenAI, Google AI)

### Installation
1. **Clone the repository**
```bash
git clone <repository_url>
cd discord-ai-bot
```

2. **Configure Environment**
```bash
# Copy example environment file
cp .env_example .env

# Edit .env file with your tokens and API keys
nano .env  # or use any text editor
```

3. **Discord Bot Setup**
- Go to [Discord Developer Portal](https://discord.com/developers/applications/)
- Create a new application
- Add a bot to your application
- Enable required privileged intents:
  - Message Content Intent
  - Server Members Intent
  - Presence Intent
- Copy the bot token to your `.env` file

4. **Start the Bot**
```bash
docker-compose up --build
```

5. **Invite Bot to Server**
- In your Discord Application's OAuth2 URL Generator
- Select scopes: `bot` and `applications.commands`
- Bot Permissions: 
  - Read Messages/View Channels
  - Send Messages
  - Read Message History
  - Use External Emojis
  - Add Reactions
  - Use Slash Commands
- Copy and use the generated URL to invite the bot

## Usage

### Basic Commands
- `!setchan` - Set the current channel for bot responses
- `!setmodel <model>` - Switch AI model (claude/gpt4/gemini)
- `!setrole <role>` - Change the bot's personality role
- `!listroles` - Display available roles
- `!listmodels` - Show available AI models
- `!status` - Display current configuration

### Admin Commands
- `!shutdown` - Shutdown the bot (owner only)
- `!listservers` - List all servers the bot is in (owner only)
- `!leaveserver <server_id>` - Leave a specific server (owner only)

### Interaction
- The bot responds to mentions (@BotName)
- Maintains conversation context for 30 messages
- Context expires after 2 hours of inactivity

## Technical Details

### Architecture
```
discord-ai-bot/
├── src/
│   ├── ai/
│   │   ├── anthropic_client.py
│   │   ├── openai_client.py
│   │   └── google_client.py
│   ├── config/
│   │   ├── roles.yaml
│   │   └── config.py
│   ├── db/
│   │   └── redis_client.py
│   ├── utils/
│   │   └── helpers.py
│   ├── bot.py
│   └── main.py
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```

### AI Configuration
- Message context: Last 10 messages per conversation
- Max tokens: 2048
- Temperature: 0.7
- Top P: 0.9
- Response timeout: 60 seconds

### Redis Configuration
- Context expiry: 2 hours
- Max context messages: 30
- Per-server settings storage

## Security

### Rate Limiting
- Built-in Discord API rate limiting
- Provider-specific API rate limits apply

### Access Control
- Channel-specific responses
- Admin-only configuration commands
- Owner-only system commands

### Data Handling
- Temporary context storage in Redis
- No permanent message storage
- Automatic context cleanup

## Troubleshooting

### Common Issues
1. **Bot Not Responding**
   - Check if bot has correct channel permissions
   - Verify channel is set with `!setchan`
   - Ensure proper intents are enabled

2. **Slow Responses**
   - Check API rate limits
   - Verify network connectivity
   - Monitor Redis performance

3. **API Errors**
   - Validate API keys
   - Check API service status
   - Review error logs

### Logging
- Error logs are printed to console
- Use Docker logs for debugging:
  ```bash
  docker-compose logs -f ai_bot
  ```

## Support
For issues and feature requests, please open an issue in the repository.

## License
MIT License

## Contributing
Contributions are welcome! Please feel free to submit a Pull Request.
