# T-19: Google Cloud setup — what you need to do

**Status:** instructions ready · **you do this once (~10 minutes)**

## In one sentence
Google only lets an app read your Gmail after you register the app in Google Cloud and approve it yourself. Here's how.

## Steps
1. Go to **console.cloud.google.com** → top bar → **New project** (name it e.g. "mini-instinct") → select it.
2. **APIs & Services → Library** → search **Gmail API** → **Enable**.
3. **APIs & Services → OAuth consent screen** (may be called "Google Auth Platform"):
   - User type: **External** → app name, your email as support and developer contact.
   - **Scopes / Data access:** add `openid`, `.../auth/userinfo.email`, `.../auth/gmail.readonly`, `.../auth/gmail.send`.
   - **Audience / Test users:** add your own Gmail address.
   - **Publish app → "In production".** In "Testing" mode Google expires your login every **7 days**; in production it doesn't. Because the app isn't verified, Google shows a warning screen when you connect: click **Advanced → Go to (app) (unsafe)**. That's expected for your own private app.
4. **APIs & Services → Credentials → Create credentials → OAuth client ID** → type **Desktop app** → create.
5. Copy the **Client ID** and **Client secret** into `.env`:
   ```
   GOOGLE_CLIENT_ID=....apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=....
   ```

## Why "Desktop app"?
Our connect script (T-20) runs on your PC and catches Google's answer on `http://localhost:8765`. "Desktop app" clients allow that without a public website.

## Next
**T-20:** run the connect script.
