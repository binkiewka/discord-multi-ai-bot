# Discord Multi-AI Bot

A versatile Discord bot that leverages multiple AI providers (Anthropic Claude, OpenAI GPT-4, and Google Gemini) with advanced context memory, role-based interactions, and image generation capabilities.

## Features

### AI Integration
- **Multiple AI Providers**
  - Anthropic Claude (claude-3-opus-20240229)
  - OpenAI GPT-4 (gpt-4-turbo-preview)
  - Google Gemini (gemini-pro)
- **Image Generation**
  - Replicate API integration for AI image generation
  - Support for detailed image prompts with Flux AI model
  - Automatic image delivery in Discord
- **Seamless Model Switching** - Switch between AI models per server (admin only)
- **Context Memory** - Maintains conversation history using Redis
- **Multi-User Support** - Multiple users can participate in the same conversation thread

### Role-Based System
- Public access to role switching - Any user can change the bot's personality
- Predefined roles with unique personalities and behaviors
- Easy to add new roles via YAML configuration

Available Roles:
- **Serious Roles**
  - Default Assistant - A helpful AI assistant
  - Concise Mode - Brief and direct responses
  - Creative Assistant - Imaginative and innovative
  - Academic Expert - Formal and scholarly
  - DIY Expert - Practical project guidance

- **Fun and Creative Roles**
  - CL4P-TP 'Badjoke' Unit 🤖 - A pun-loving robot stuck in dad joke mode
  - Nutty McNutface 🐿️ - A conspiracy theorist squirrel
  - SpongeBot SquarePants 🧽 - Underwater optimist with Bikini Bottom logic
  - The Chaos Jester 🤡 - Mischievous meme-loving absurdist
  - Reality Fracture v3.14 🔮 - Multi-dimensional metaphysical entity

- **Specialized Roles**
  - Flux AI - Expert image prompt engineer
  - Poet - Emotional verse creator
  - Rapper - Lyrical wordsmith
  - Dream Interpreter - Analytical dream analyst
  - Domain Generator - Creative naming expert

### Server Management
- **Channel-Specific Responses** - Bot only responds in designated channels
- **Per-Server Configuration** - Each server maintains its own settings
- **Admin Controls** - Server administrators can manage critical bot settings
- **Debug Tools** - Advanced debugging capabilities for bot owners

## Setup

### Prerequisites
- Docker and Docker Compose
- Discord Bot Token
- AI Provider API Keys:
  - Anthropic API Key
  - OpenAI API Key
  - Google AI API Key
  - Replicate API Token

### Installation
1. **Clone the repository**
```bash
git clone https://github.com/yourusername/discord-multi-ai-bot
cd discord-multi-ai-bot
```

2. **Configure Environment**
```bash
# Copy example environment file
cp .env_example .env

# Edit .env file with your tokens and API keys
nano .env  # or use any text editor
```

Required environment variables:
```env
DISCORD_TOKEN=your_discord_token
ANTHROPIC_API_KEY=your_anthropic_key
OPENAI_API_KEY=your_openai_key
GOOGLE_API_KEY=your_google_key
REPLICATE_API_TOKEN=your_replicate_token
OWNER_ID=your_discord_id
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
- Generate OAuth2 URL with required permissions:
  - Read Messages/View Channels
  - Send Messages
  - Read Message History
  - Use External Emojis
  - Add Reactions
  - Attach Files (for image generation)

## Usage

### Public Commands
- `!setrole <role>` - Change the bot's personality (available to all users)
- `!listroles` - Display available personality roles
- `!listmodels` - Show available AI models
- `!image <prompt>` - Generate an image from a text prompt

### Admin Commands
- `!setchan` - Set the current channel for bot responses
- `!setmodel <model>` - Switch AI model (claude/gpt4/gemini)
- `!status` - Display current configuration

### Owner Commands
- `!debug` - View Redis debug information
- `!clearredis` - Clear all Redis data
- `!shutdown` - Shutdown the bot
- `!listservers` - List all servers the bot is in
- `!leaveserver <server_id>` - Leave a specific server

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
│   │   ├── google_client.py
│   │   └── replicate_client.py
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
- Image generation via Replicate API

### Redis Configuration
- Context expiry: 2 hours
- Max context messages: 30
- Per-server settings storage
- Debug tools for data inspection

## Security

### Permission Levels
- **Public Access**
  - Role selection
  - Image generation
  - Basic informational commands
- **Admin Access**
  - Model selection
  - Channel configuration
  - Status monitoring
- **Owner Access**
  - Debug tools
  - Redis management
  - Server management

### Rate Limiting
- Built-in Discord API rate limiting
- Provider-specific API rate limits apply
- Image generation throttling

### Data Handling
- Temporary context storage in Redis
- No permanent message storage
- Automatic context cleanup
- Secure API key management

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

3. **Image Generation Failures**
   - Verify Replicate API token
   - Check prompt guidelines
   - Monitor API quotas

### Logging
- Error logs are printed to console
- Debug command for Redis inspection
- Use Docker logs for debugging:
  ```bash
  docker-compose logs -f ai_bot
  ```

## Support
For issues and feature requests, please open an issue in the repository.

## License
GPL-3.0 license

## Contributing
Contributions are welcome! Please feel free to submit a Pull Request.
