# iMessage GPT Bot

A macOS bot that monitors iMessage chats and responds to messages using OpenAI's GPT models. The bot listens for messages prefixed with a trigger (e.g., "@zbot") and sends AI-generated replies back to the conversation.

## Features

- 🤖 **AI-Powered Responses**: Uses OpenAI's GPT models to generate contextual responses
- 💬 **iMessage Integration**: Monitors and responds to messages in real-time
- 📱 **Contact Resolution**: Optionally resolves phone numbers and emails to contact names
- 🔍 **Interactive Chat Picker**: Select from recent chats with filtering and search
- 📊 **Message History**: Maintains conversation context for better responses
- ⚡ **Smart Rate Limiting**: Handles API rate limits with exponential backoff

## Requirements

- **macOS**: Required for accessing Messages database and Contacts framework
- **Python 3.7+**: Tested with Python 3.7 and later
- **OpenAI API Key**: Set in the `OPENAI_API_KEY` environment variable
- **Messages.app**: Must have an existing Messages database

### Python Dependencies

Install required packages:

```bash
pip install openai pyobjc-framework-Contacts
```

Or using a requirements file:

```bash
pip install -r requirements.txt
```

## Installation

1. **Clone or download** this repository

2. **Install dependencies**:
   ```bash
   pip install openai pyobjc-framework-Contacts
   ```

3. **Set your OpenAI API key**:
   ```bash
   export OPENAI_API_KEY='sk-proj-...'
   ```

4. **Make the script executable** (optional):
   ```bash
   chmod +x zbot.py
   ```

## Usage

### Basic Usage

Run the bot and select a chat interactively:

```bash
python zbot.py
```

This will display a list of recent chats for you to choose from.

### Command Line Options

```bash
python zbot.py [OPTIONS]
```

**Options:**

- `--hint TEXT`: Filter chats by substring (searches name, identifier, or contact name)
- `--chat-id INTEGER`: Skip the picker and run directly for a specific chat ID
- `--with-contacts`: Enable contact name resolution (requires Contacts framework)
- `--limit INTEGER`: Number of recent chats to show in picker (default: 30)

### Examples

**Select from chats matching "John":**
```bash
python zbot.py --hint "John"
```

**Run directly for a specific chat:**
```bash
python zbot.py --chat-id 12345
```

**Use contact name resolution:**
```bash
python zbot.py --with-contacts
```

**Combine options:**
```bash
python zbot.py --hint "work" --with-contacts --limit 20
```

## How It Works

### Architecture

The bot is organized into several key components:

1. **MessagesDatabase**: Handles read-only access to the Messages `chat.db` database
2. **ContactsManager**: Manages contact lookup using macOS Contacts framework
3. **OpenAIClient**: Interfaces with OpenAI API for generating responses
4. **MessageSender**: Sends messages via AppleScript to Messages.app
5. **ChatPicker**: Provides interactive chat selection interface
6. **iMessageBot**: Main bot class that orchestrates monitoring and responding

### Message Flow

1. **Polling**: The bot polls the Messages database every 2 seconds for new messages
2. **Detection**: When a message starts with the trigger prefix (default: `@zbot`), the bot processes it
3. **Processing**: The bot:
   - Extracts the user's prompt (removes the trigger prefix)
   - Sends it to OpenAI with conversation history
   - Receives the AI-generated response
4. **Sending**: The bot sends the response back to the chat via AppleScript
5. **Cooldown**: A 6-second cooldown prevents rapid-fire responses

### Message Format

The bot responds to messages that start with the trigger prefix (default: `@zbot`):

```
@zbot What's the weather like?
```

The bot will respond with:
```
🤖 [AI-generated response]
```

### Configuration

Edit the constants at the top of `zbot.py` to customize:

- `BOT_PREFIX`: Trigger prefix (default: `"@zbot"`)
- `BOT_OUT_PREFIX`: Prefix for bot responses (default: `"🤖 "`)
- `MODEL`: OpenAI model to use (default: `"gpt-4o-mini"`)
- `POLL_SECONDS`: How often to check for new messages (default: `2`)
- `COOLDOWN_SECONDS`: Minimum time between responses (default: `6`)
- `MAX_CONTEXT_MESSAGES`: Maximum conversation history to keep (default: `20`)

## Database Access

The bot reads from the Messages database located at:
```
~/Library/Messages/chat.db
```

This is a read-only connection - the bot never modifies your messages. The database is accessed via SQLite with proper connection handling and timeouts.

## Contact Resolution

When `--with-contacts` is enabled, the bot:
- Loads contacts from macOS Contacts.app
- Maps phone numbers and emails to contact names
- Displays friendly names in the chat picker
- Normalizes phone numbers to E.164 format

This requires the `pyobjc-framework-Contacts` package and proper permissions.

## Error Handling

The bot includes robust error handling for:

- **Rate Limiting**: Automatic retry with exponential backoff
- **API Errors**: Clear error messages for authentication, quota, and other issues
- **Database Errors**: Graceful handling of locked or unavailable databases
- **Message Sending**: Logs failures but continues running

## Limitations

1. **macOS Only**: Requires macOS for Messages database and Contacts framework access
2. **Read-Only Database**: Only reads from Messages database (never writes)
3. **AppleScript Dependency**: Message sending requires Messages.app to be running
4. **Rate Limits**: Subject to OpenAI API rate limits and quotas
5. **Single Chat**: Bot monitors one chat at a time (run multiple instances for multiple chats)

## Troubleshooting

### "Missing OPENAI_API_KEY"
Set your API key as an environment variable:
```bash
export OPENAI_API_KEY='your-key-here'
```

### "Contacts framework not available"
Install the Contacts framework:
```bash
pip install pyobjc-framework-Contacts
```

### "No recent chats matched"
- Try removing the `--hint` filter
- Check that Messages.app has chats
- Verify database path is correct

### Messages not sending
- Ensure Messages.app is running
- Check that the chat name matches exactly (especially for group chats)
- Verify you have permission to send messages

### Bot responds to old messages
The bot initializes `last_seen_id` from the most recent message when it starts. Only messages after that point will trigger responses.

## Security Considerations

- **API Key**: Never commit your OpenAI API key to version control
- **Database**: The bot only reads from the database (never writes)
- **Permissions**: Requires access to Messages database and Contacts (macOS may prompt)
- **Messages**: All message content is sent to OpenAI API (review OpenAI's privacy policy)

## License

This project is provided as-is for personal use. Use at your own risk.

## Contributing

Feel free to submit issues, fork, and create pull requests for improvements.

## Disclaimer

This bot interacts with your personal messages and sends content to third-party APIs (OpenAI). Use responsibly and be aware of privacy implications. The authors are not responsible for any misuse or data exposure.
