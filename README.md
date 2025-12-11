# Discord Multi-AI Bot

A versatile Discord bot that leverages multiple AI providers (Anthropic Claude, OpenAI GPT-4, and Google Gemini) with advanced context memory, role-based interactions, and image generation capabilities.

## Features

### AI Integration
- **Multiple AI Providers**
  - Anthropic Claude
  - OpenAI GPT-4
  - Google Gemini
- **Image Generation**
  - `!flux` - Fast image generation using Flux Schnell model
  - `!fluxpro` - High-quality image generation using Flux Pro model
  - `!recraft` - Advanced image generation using ReCraft v3
  - Support for detailed image prompts
  - Automatic image delivery in Discord
- **Games**
  - Countdown Numbers Game - Classic TV show-style math puzzle game
  - **Discord Activity** - Play directly inside Discord voice channels with a modern UI
  - Competitive multiplayer rounds with configurable time limits
  - Secure expression parser (no code injection)
- **Channel-Specific Configuration** - Set different AI models and roles per channel (admin only)
- **Seamless Model Switching** - Switch between AI models with automatic fallback to server-wide defaults
- **Context Memory** - Maintains conversation history using Redis
- **Multi-User Support** - Multiple users can participate in the same conversation thread

### Role-Based System
- **Channel-Specific Roles** - Each channel can have its own AI personality (admin controlled)
- **Flexible Fallback System** - Channel-specific → Server-wide → Default role
- Predefined roles with unique personalities and behaviors
- Easy to add new roles via YAML configuration

Available Roles:
- **Core Assistants**
  - Default Assistant - A helpful AI assistant
  - Concise Assistant - Direct and brief responses
  - Creative Assistant - Imaginative and innovative perspectives
  - Academic Assistant - Formal and scholarly responses with citations
  - DIY Expert - Clear guidance for home improvement projects

- **Entertainment & Humor**
  - Comedian - Witty stand-up comedy routines
  - CL4P-TP 'Badjoke' Unit 🤖 - A pun-loving robot stuck in dad joke mode
  - The Chaos Jester 🤡 - Mischievous meme-loving absurdist
  - Lunatic - Deliberately nonsensical and arbitrary responses
  - Nutty McNutface 🐿️ - Conspiracy theorist squirrel
  - SpongeBot SquarePants 🧽 - Underwater optimist with Bikini Bottom logic

- **Creative & Artistic**
  - Poet - Emotionally resonant verses and poetry
  - Rapper - Powerful and meaningful lyrics with rhythm
  - Reality Fracture v3.14 🔮 - Multi-dimensional metaphysical entity

- **Specialized Tools**
  - Dream Interpreter - Analytical dream symbolism analysis
  - Domain Generator - Creative short domain name creation

### Server Management
- **Multi-Channel Support** - Bot can respond in multiple designated channels per server
- **Channel-Specific Configuration** - Each channel can have unique AI model and role settings
- **Per-Server Configuration** - Server-wide settings act as fallback for channels without specific configuration
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
git clone https://github.com/binkiewka/discord-multi-ai-bot
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
DISCORD_CLIENT_ID=your_application_client_id
DISCORD_CLIENT_SECRET=your_oauth2_client_secret
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
  - Add Reactions
  - Attach Files (for image generation)

6. **Discord Activity Setup (Required for Numbers Game)**

The Numbers Game runs as a Discord Activity embedded inside voice channels.

**Discord Developer Portal Configuration:**
1. Go to [Discord Developer Portal](https://discord.com/developers/applications/)
2. Select your bot application
3. Copy **Client ID** from OAuth2 section → Add to `.env` as `DISCORD_CLIENT_ID`
4. Generate **Client Secret** (OAuth2 > General) → Add to `.env` as `DISCORD_CLIENT_SECRET`
5. Enable **Activities** (Activities section in sidebar) → Toggle ON
6. Configure **URL Mappings** (Activities > URL Mappings):
   ```
   Prefix: /api
   Target: your-api-domain.com (pointing to port 10010)
   ```
7. Set **Activity URL** to your Activity frontend domain (pointing to port 10011)

**Caddy/Nginx Setup:**
Set up reverse proxies for both services:
```
# Activity Frontend (port 10011)
activity.yourdomain.com {
    reverse_proxy localhost:10011
}

# Bot API (port 10010)
api.yourdomain.com {
    reverse_proxy localhost:10010
}
```

## Usage

### Public Commands
- `!listroles` - Display available personality roles
- `!listmodels` - Show available AI models
- `!channelconfig` - Show current channel's AI configuration (role and model)
- `!channelconfig <#channel>` - Show specific channel's AI configuration
- `!flux <prompt>` - Generate image using Flux Schnell model
- `!fluxpro <prompt>` - Generate high-quality image using Flux Pro
- `!recraft <prompt>` - Generate image using ReCraft v3

### Game Commands
- `!countdown` / `!numbers` - Start a new Countdown Numbers Game

**Countdown Numbers Game:**
A classic TV show-style math puzzle that runs as a **Discord Activity** inside voice channels.

**How to Play:**
1. Use `!countdown` or `!numbers` to start a game lobby
2. Configure rounds (1-5) and time per round (30/60/120 seconds)
3. Players click "Ready" to join
4. Host clicks "Start Game"
5. **Join a voice channel** and click "Play in Discord" to launch the Activity
6. Build mathematical expressions using the available numbers to reach the target
7. Submit your answer before time runs out!

**Game Rules:**
- Target number: 100-999
- 6 numbers available (2 large: 25/50/75/100, 4 small: 1-10)
- Use `+`, `-`, `×`, `÷` and parentheses
- Each number can only be used once
- Closest to target wins! (Exact match = 10 points, within 10 = 5 points, within 25 = 2 points)

### Admin Commands

#### Channel Management
- `!addchan` - Add current channel to allowed channels
- `!addchan <#channel>` - Add specified channel to allowed channels
- `!mute` - Remove current channel from allowed channels
- `!mute <#channel>` - Remove specified channel from allowed channels
- `!listchans` - List all channels where bot will respond
- `!clearchans` - Remove all allowed channels

#### AI Configuration (Channel-Specific)
- `!setrole <role>` - Set AI personality for current channel
- `!setrole <role> <#channel>` - Set AI personality for specific channel
- `!setmodel <model>` - Set AI model for current channel (claude/gpt4/gemini)
- `!setmodel <model> <#channel>` - Set AI model for specific channel
- `!clearchannelconfig` - Clear channel-specific settings for current channel (reverts to server-wide)
- `!clearchannelconfig <#channel>` - Clear channel-specific settings for specific channel

#### Server-Wide Defaults
- `!setdefaultrole <role>` - Set server-wide default AI personality (fallback for channels without specific settings)
- `!setdefaultmodel <model>` - Set server-wide default AI model (fallback for channels without specific settings)
- `!status` - Display server defaults and all channel-specific configurations

**Note:** Channel-specific settings take priority over server-wide defaults. If no channel-specific setting exists, the bot falls back to server-wide defaults, then to hardcoded defaults.

**Permissions:** All admin commands require Administrator or Moderator permissions (or bot owner).

### Owner Commands
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
│   │   ├── base_image_client.py
│   │   ├── flux_client.py
│   │   ├── fluxpro_client.py
│   │   └── recraft_client.py
│   ├── assets/
│   │   └── countdown_banner.jpg
│   ├── config/
│   │   ├── roles.yaml
│   │   └── config.py
│   ├── db/
│   │   └── redis_client.py
│   ├── games/
│   │   ├── __init__.py
│   │   ├── countdown.py
│   │   ├── expression_parser.py
│   │   └── solver.py
│   ├── utils/
│   │   └── helpers.py
│   ├── bot.py
│   └── main.py
├── activity-client/          # Discord Activity Frontend
│   ├── src/
│   │   ├── main.ts           # Discord SDK integration
│   │   └── style.css         # Modern dark theme UI
│   ├── index.html
│   ├── package.json
│   ├── vite.config.ts
│   └── Dockerfile
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
- Response timeout: 120 seconds
- Image generation via Replicate API

### Redis Configuration
- Context expiry: 2 hours
- Max context messages: 30
- Per-server and per-channel settings storage
- Automatic fallback chain: channel-specific → server-wide → defaults
- Debug tools for data inspection

## Security

### Permission Levels
- **Public Access**
  - Image generation
  - Basic informational commands
  - View channel configurations
- **Admin/Moderator Access**
  - Role selection (channel-specific and server-wide defaults)
  - Model selection (channel-specific and server-wide defaults)
  - Channel configuration (add/remove allowed channels)
  - Status monitoring (view all configurations)
  - Requires Administrator OR Moderator permissions
- **Owner Access**
  - Debug tools
  - Redis management
  - Server management
  - Shutdown command

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
   - Verify channel is added with `!addchan` (use `!listchans` to see allowed channels)
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
