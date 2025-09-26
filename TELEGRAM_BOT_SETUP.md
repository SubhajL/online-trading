# Telegram Bot Setup Guide

## Your Bot Information
- **Bot Token**: `8289541020:AAHd-sruzaADQO_3-aQ-6-C6_5izZ6s5edI`

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
TELEGRAM_BOT_TOKEN=8289541020:AAHd-sruzaADQO_3-aQ-6-C6_5izZ6s5edI
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