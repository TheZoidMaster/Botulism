# Botulism

Discord AI Chatbot Framework

Config is stored in config.json. You can set the bot token, prefix, and other settings there.

## Config file contents:

-   **token**: A string representing the authentication token. This is a sensitive value and should be kept secure.
-   **name**: The name of the bot, represented as a string. This is used for triggering a resposne without pinging the bot
-   **status**: A string to be used as the bot's status.
-   **model**: Specifies the AI model being used, represented as a string. Example: "llama3.1". You must have the model pre-pulled in ollama before this will work.
-   **temperature**: A numeric value that controls the randomness of the bot's responses. Higher values (e.g., 1.5) result in more creative outputs.
-   **prefix**: A string defining the command prefix for the bot. For example, "b!".
-   **system**: A detailed string containing the bot's system instructions, personality, and behavioral guidelines. This includes how the bot should interact with users and specific stylistic rules.
-   **append_default_system**: A boolean indicating whether the default system instructions should be appended to the bot's configuration. `true` means they will be appended.
-   **history_limit**: An integer specifying the maximum number of messages to retain in the bot's conversation history. Example: 40.
