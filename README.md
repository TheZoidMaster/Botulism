> [!IMPORTANT]  
> This has been depricated in favor of [Hivemind](https://github.com/TheZoidMaster/Hivemind).

# Botulism

a Discord AI chatbot template

Config is stored in `config.json`. Set the bot token, prefix, and other settings in this file.

## Config File Contents

-   **token**:  
     A string representing the authentication token. Keep this secure!

-   **name**:  
     The bot's name as a string. It is used for invoking responses without pinging.

-   **status**:  
     A string that defines the bot’s current status.

-   **model**:  
     A string specifying the AI model in use (e.g., "llama3.1"). Ensure the model is pre-pulled in ollama.

-   **temperature**:  
     A numeric value controlling response randomness. Higher values (e.g., 1.5) produce more creative outputs.

-   **prefix**:  
     A string that defines the command prefix (e.g., "b!").

-   **system**:  
     A detailed string that outlines system instructions, personality, and behavioral guidelines.

-   **append_default_system**:  
     A boolean indicating if default system instructions should be appended (`true` means they will be).

-   **history_limit**:  
     An integer specifying the maximum number of messages to retain in the conversation history (e.g., 40).

-   **always_respond_channel_id**:  
     A string representing the channel ID where the bot will always respond, regardless of if it gets pinged or not.
