# WC 2026 Mobile App (Expo)

**Designed by Amit Tavor** · Research only — not betting advice.

Native mobile app for the WC 2026 predictor. Connects to the FastAPI backend on Render.

## Prerequisites

- [Node.js](https://nodejs.org/) 18+
- [Expo Go](https://expo.dev/go) on your phone (App Store / Play Store)
- Backend deployed on Render (see root `DEPLOY.md`)

## Setup

```bash
cd mobile
npm install
```

Copy the root env template (one `.env` for backend + mobile):

```bash
cp ../.env.example ../.env
```

Edit **`../.env`** (project root) — at minimum set:

```env
EXPO_PUBLIC_API_URL=https://your-api.onrender.com
```

## Run on your phone

```bash
npm start
```

1. Scan the QR code with **Expo Go** (Android) or Camera app (iOS)
2. App loads on your phone from anywhere — no same WiFi needed

## Tabs

| Tab | Description |
|-----|-------------|
| **Matches** | Upcoming fixtures + AI picks (pull to refresh) |
| **Live** | Live scores |
| **Results** | Recent finished matches |

Tap any match for full prediction explanation, injuries, and lineups.

## Build standalone app (optional)

```bash
npx eas build --platform ios
npx eas build --platform android
```

Requires [Expo Application Services](https://expo.dev/eas) account.

## Local API for development

```bash
# From project root:
uvicorn api_server:app --reload --port 8000
```

Then set `EXPO_PUBLIC_API_URL=http://YOUR_MAC_IP:8000` in the **project root** `.env` for device testing on same network, or use Render URL for remote.
