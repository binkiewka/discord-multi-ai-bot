# Discord Activity Setup Guide

To run the Numbers Game as an embedded **iframe** (Discord Activity) inside a voice channel or text channel, you must configure your application in the Discord Developer Portal.

## Prerequisites
1.  **HTTPS URL**: Your game must be accessible via HTTPS (which you have configured via Caddy).
2.  **Discord Developer Account**: You must be the owner of the bot application.

## Step 1: Developer Portal Configuration
1.  Go to the [Discord Developer Portal](https://discord.com/developers/applications/).
2.  Select your Application.
3.  Go to the **Activities** tab in the sidebar (if available) or **App Details**.
    *   *Note: Discord has been moving these settings. Look for "Embedded App" or "Activities".*
4.  **URL Mappings**:
    *   Add a new Mapping.
    *   **Prefix**: `/`
    *   **Target URL**: `https://your-game-domain.com` (The `PUBLIC_GAME_URL` you set).
5.  **OAuth2**:
    *   Go to **OAuth2**.
    *   Add the Redirect: `https://your-game-domain.com`.

## Step 2: Enable Activities
1.  In the Developer Portal, ensure your app is enabled as an **Activity** if there is a specific toggle.
2.  Copy your **Application ID**.

## Step 3: Launching
Once configured, you can launch the activity in a few ways:
1.  **Voice Channel**: Join a VC, click the "Rocket" icon (Activities), and if your app is in development/authorized, you should see it.
2.  **Link**: A link to `https://discord.com/activities/<YOUR_APP_ID>` might work if supported.

## Important Note on Context
Currently, the game uses URL parameters (`?user=ID`) to know who you are.
When running as an Activity, Discord *might* strip these parameters or load the root URL.
If the game loads but says "User not found" or "Invalid ID", we will need to upgrade the frontend to use the **Discord Embedded App SDK** for authentication.
