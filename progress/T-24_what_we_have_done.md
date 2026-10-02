# T-24: Browser container with live view — what we have done

**Status:** done ✅ (built and smoke-tested in Docker)

## In one sentence
We built a Docker container that runs a **real Google Chrome on a virtual screen**, which you can **watch and control from your web browser** at `http://localhost:6080/vnc.html`.

## What's inside the container (`docker/browser.Dockerfile`)
| Piece | Job |
|---|---|
| **Xvfb** | A fake screen (1440×900) for Chrome to draw on |
| **fluxbox** | A tiny window manager so windows behave |
| **Google Chrome** | Real Chrome (not the test "Chromium"), so fewer sites say "unsupported browser" |
| **x11vnc** | Shares the screen, **only inside the container** (localhost), password-protected |
| **noVNC + websockify** | Turns that into a web page on port 6080 |
| **Our browser worker** | Launches Chrome and drives it (T-26) |

`docker/browser-entrypoint.sh` starts them in order. It **refuses to start without `VNC_PASSWORD`**, and it clears Chrome's leftover lock files if the container was killed.

## Safety
- Port **6080** is published only to `127.0.0.1` (your PC). VNC's own port 5900 is never published; inside the container it listens only on localhost.
- The Chrome **profile** (your logins) lives on the `browser-profile` Docker volume and never leaves your PC.
- Chrome starts **without the "automation" flags**, so sites see a normal browser, and it can't download files.

## Smoke tests (in the real container, all passed)
| Check | Result |
|---|---|
| Chrome opens example.com, page elements listed | ✅ `[1] link "Learn more"` |
| `navigator.webdriver` (how sites detect bots) | ✅ **false** |
| "Headless" in the user agent | ✅ no |
| Logged-in state survives a Chrome restart | ✅ yes |
| Live view page at http://127.0.0.1:6080/vnc.html | ✅ HTTP 200 |
| VNC port 5900 reachable from your PC | ✅ no, container-only |

## Things to know
- **VNC passwords are max 8 characters.** VNC's own password security is weak, which is why the live view is only on your PC (and on your phone via Tailscale, T-25), never on the internet.
- **Give Docker about 6 GB of RAM** (README) before running the browser all the time. Chrome is the hungriest part.

## Credentials needed
`VNC_PASSWORD=` (up to 8 characters) in `.env`.

## How to check it yourself
```sh
docker compose up -d browser
```
Then open http://localhost:6080/vnc.html, enter the VNC password, and you'll see Chrome. Log into any site you want the agent to use.

## Next
**T-25:** see the live view on your phone (Tailscale).
