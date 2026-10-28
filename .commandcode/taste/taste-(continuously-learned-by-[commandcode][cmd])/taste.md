# Taste (Continuously Learned by [CommandCode][cmd])
- Writes code and prompts in Polish (bot commands, comments, prompt text). Confidence: 0.9
- Prefers detailed, structured task specifications with explicit implementation steps rather than vague requirements. Confidence: 0.8
- Prioritizes robust edge-case handling and fallback logic when parsing LLM output (e.g., if delimiter is missing, fall back to character-count-based splitting, then paragraph-boundary splitting). Confidence: 0.8
- Cares about respecting Discord's character limits and wants message-splitting logic that avoids truncation. Confidence: 0.8
- Prefers using current Google GenAI SDK APIs (Client-based pattern over legacy configure-based pattern) and proactively migrates away from deprecated interfaces. Confidence: 0.7
- Uses `@app_commands.choices` with descriptive, localized Polish names for enum-like slash command parameters. Confidence: 0.6
- Prefers factoring variable prompt construction into a dedicated function rather than keeping prompts as module-level constants when they need to differ by parameter. Confidence: 0.6
