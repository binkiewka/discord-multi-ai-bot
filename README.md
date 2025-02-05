# Discord Multi-AI Bot

A versatile Discord bot that leverages multiple AI providers (Anthropic Claude, OpenAI GPT-4, and Google Gemini) with advanced context memory, role-based interactions, and image generation capabilities.

## Features

### AI Integration
- **Multiple AI Providers**
  - Anthropic Claude
  - OpenAI GPT
  - Google Gemini
  - Replicate Flux (image generation)
- **Seamless Model Switching** - Switch between AI models per server
- **Context Memory** - Maintains conversation history using Redis
- **Multi-User Support** - Multiple users can participate in the same conversation thread

### Image Generation
- **Direct Image Commands** - Generate images using the `!image` command without switching models
- **High-Quality Output** - Optimized settings for detailed 1024x768 images
- **Advanced Parameters** - Customized negative prompting and quality settings
- **Safety Filters** - Built-in content safety checking

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
- AI Provider API Keys:
  - Anthropic API Key
  - OpenAI API Key
  - Google AI API Key
  - Replicate API Token (for image generation)

### Installation
1. **Clone the repository**
```bash
git clone https://github.com/binkiewka/discord-multi-ai-bot
cd discord-ai-bot
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
DISCORD_TOKEN=your_discord_bot_token
ANTHROPIC_API_KEY=your_anthropic_api_key
OPENAI_API_KEY=your_openai_api_key
GOOGLE_API_KEY=your_google_api_key
REPLICATE_API_TOKEN=your_replicate_api_token
OWNER_ID=your_discord_user_id
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
  - Attach Files
  - Use Slash Commands
- Copy and use the generated URL to invite the bot

## Usage

### Basic Commands
- `!setchan` - Set the current channel for bot responses
- `!setmodel <model>` - Switch AI model (claude/gpt4/gemini)
- `!setrole <role>` - Change the bot's personality role
- `!image <prompt>` - Generate an image from text prompt
- `!listroles` - Display available roles
- `!listmodels` - Show available AI models
- `!status` - Display current configuration

### Image Generation
The bot supports direct image generation through the `!image` command:
```bash
!image a beautiful sunset over mountains, photorealistic, 4k
```

Image generation features:
- High-quality 1024x768 output
- Advanced negative prompting
- Content safety filters
- Multiple inference steps for better quality
- Optimized guidance scaling

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

### Image Generation Configuration
- Resolution: 1024x768 (4:3 aspect ratio)
- Inference steps: 50
- Guidance scale: 7.5
- Scheduler: DPMSolverMultistep
- Safety checker: Enabled
- Negative prompting: Configured for quality output

### Redis Configuration
- Context expiry: 2 hours
- Max context messages: 30
- Per-server settings storage

## Security

### Rate Limiting
- Built-in Discord API rate limiting
- Provider-specific API rate limits apply
- Image generation request limiting

### Access Control
- Channel-specific responses
- Admin-only configuration commands
- Owner-only system commands

### Data Handling
- Temporary context storage in Redis
- No permanent message storage
- Automatic context cleanup
- Secure image generation with content filtering

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

4. **Image Generation Issues**
   - Verify Replicate API token
   - Check prompt length and content
   - Ensure bot has file attachment permissions
   - Monitor Replicate service status

### Logging
- Error logs are printed to console
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
