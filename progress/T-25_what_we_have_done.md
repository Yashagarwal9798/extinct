# T-25: Live view on your phone (Tailscale) — what you need to do

**Status:** instructions ready · **optional, you do this once (~5 minutes)**

## In one sentence
Tailscale makes a **private network** between your PC and your phone, so you can open the browser's live view on your phone **without exposing anything to the internet**.

## Why Tailscale
The live view must never be public: whoever reaches it controls every account logged into that Chrome. Tailscale lets only **your own devices** (signed into your account) reach it, from anywhere, with HTTPS. It's free for personal use.

## Steps
1. Install **Tailscale** on your PC (tailscale.com/download) and on your phone (App Store / Play Store). Sign in with the **same account** on both.
2. On the PC, in a terminal:
   ```sh
   tailscale serve --bg --https=443 http://127.0.0.1:6080
   ```
   It prints an address like `https://your-pc.tail1234.ts.net`. (If the command differs in your Tailscale version, run `tailscale serve --help`.)
3. Put this in `.env` (the agent sends this link when it needs you to take over):
   ```
   LIVE_VIEW_URL=https://your-pc.tail1234.ts.net/vnc.html?autoconnect=1&resize=scale
   ```
4. Restart: `docker compose up -d`

## Check it
- On your phone, **on mobile data** (not your Wi-Fi), open the link → enter the VNC password → you see Chrome.
- From a device **not** in your Tailscale account, the link doesn't load.

## Without Tailscale
Everything still works. The takeover link just points to `http://localhost:6080/vnc.html`, which only opens on the PC itself.

## Next
**T-26:** the browser worker.
