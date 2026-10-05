# telegram

Telegram channel for the Veles daemon: talk to your agent from a Telegram bot.

## Install

Declare the channel and the daemon installs the module on its next start:

```toml
# .veles/config.toml
[channels.telegram]
enabled = true
whitelist = ["123456789"]   # chat ids allowed to talk to the bot; empty = anyone
```

Or set it up interactively — `veles channel add telegram` asks for the bot token
(from @BotFather) and stores it in the OS keychain. By hand:
`veles registry install telegram`.

## Settings

| key | meaning |
|---|---|
| `bot_token` | the bot's token; kept in the keychain, or `TELEGRAM_BOT_TOKEN` for `veles channel run` |
| `whitelist` | chat ids the bot answers |
| `debounce_seconds` | how long to wait for more of a split message (default 3) |
| `forward_debounce_seconds` | the same for forwards and albums (default 12) |

## In the chat

Answers stream in place. Trust and approval prompts, and the agent's own questions,
arrive with buttons. Voice and images are described when the project has STT /
vision routes. Commands: `/mode`, `/goal`, `/settings`, `/tokens`, `/context`,
`/status`, `/session`, `/insights`, `/rules`, `/dream`, `/reset`, `/help`. Scheduled jobs deliver to
`telegram:<chat_id>`.
