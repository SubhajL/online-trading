# Telegram Bot Setup Guide

## Your Bot Information
- **Bot Token**: See `.env` file (never commit real tokens to git)

> ⚠️ **SECURITY WARNING**: The token that was previously in this file has been rotated.
> If you see a real token here in git history, it has been compromised and revoked.
> Always store tokens only in `.env` files (which are gitignored).
>
> **To rotate a compromised token:**
> 1. Open Telegram and message `@BotFather`
> 2. Send `/revoke` and select your bot
> 3. Generate a new token with `/token`
> 4. Update your `.env` file with the new token

## Steps to Complete Setup:

### 1. Find Your Bot in Telegram
- Open Telegram app
- In the search bar, look for your bot by its username (given by BotFather)
- It will have a name like `@YourBotName_bot`

### 2. Start Conversation with Your Bot
- Click on your bot
- Press "START" button or send `/start`
- Send any message like "Hello"

### 3. Get Your Chat ID
```bash
cd /Users/subhajlimanond/dev/online\ trader
source venv/bin/activate
python scripts/get_telegram_chat_id.py
```

### 4. Update Your Environment File
Once you have your chat ID, update your `.env` file:
```bash
TELEGRAM_BOT_TOKEN=YOUR_BOT_TOKEN_HERE
TELEGRAM_CHAT_ID=YOUR_CHAT_ID_HERE
```

### 5. Test the Bot
```bash
python scripts/test_telegram_bot.py
```

## Security Warning
⚠️ **NEVER share your bot token publicly!** Anyone with the token can control your bot.

## Troubleshooting

### Bot Not Responding?
1. Make sure you created the bot correctly with BotFather
2. Check that the token is correct
3. Ensure you've started a conversation with the bot

### Can't Find Bot?
1. Go back to BotFather
2. Send `/mybots`
3. Select your bot to see its username

### Rate Limiting?
- Telegram limits: 30 messages/second to different chats
- 20 messages/minute to same chat
- The delivery service handles this automatically