# Configuration Profile Guide

## Configuration File Location

The macOS app bundle saves configuration to `~/Library/Application Support/AIExamGrader/config.json`. The directory is created when saving, and the same file is used after moving or rebuilding the app. New configuration files are readable and writable only by the current user.

To reuse a source installation's configuration, quit the app and copy its existing `config.json` to this location. Back up an existing destination before replacing it. Running from source continues to use `config.json` in the working directory; the quick start below applies to source installations.

## Quick Start

1. Copy `config_example.json` to `config.json`:
   ```bash
   cp config_example.json config.json
   ```

2. Edit `config.json` with your actual API keys and file paths

3. Launch the application - it will auto-load the last used profile

## Global Settings

These settings apply to the entire application:

- **language**: Interface language.
    - `"CN"`: Simplified Chinese (Default)
    - `"EN"`: English

## Profile Structure

Each profile can save:
- **provider**: "Gemini" or "OpenAI"
- **api_key**: Your API key
- **base_url**: Optional base URL for API
- **model**: Model name (e.g., "gemini-2.5-pro-maxthinking", "gpt-4o")
- **rubric_path**: Path to grading rubric file
- **exam_folder**: Path to answer sheet images folder
- **student_list**: Path to student list Excel file

## Using Profiles

### In the Application
1. Select profile from dropdown in sidebar
2. All settings load automatically
3. Click "💾 Save" to save current settings as a new profile
4. Click "🗑️ Delete" to remove selected profile

### Manual Editing
You can also edit `config.json` directly:

```json
{
    "profiles": {
        "Profile Name": {
            "provider": "Gemini",
            "api_key": "your-key",
            "model": "gemini-2.5-pro-maxthinking",
            ...
        }
    },
    "last_used": "Profile Name"
}
```

## Example Use Cases

- **Multiple Exams**: Different profiles for Math, English, Physics exams
- **Multiple API Providers**: Switch between Gemini and OpenAI
- **Testing**: Separate profiles for production and testing
- **Team Sharing**: Share profiles (remember to remove API keys!)

## Security Note

⚠️ **Important**: The `config.json` file is gitignored by default to protect your API keys. Never commit your actual API keys to version control.
