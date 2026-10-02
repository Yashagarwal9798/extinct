# T-04: Local encrypted secrets store — what we have done

**Status:** done ✅ (no credentials needed)

## In one sentence
We built a small **locked box** on your PC (`secrets.db`) where passwords and tokens are stored **only in scrambled (encrypted) form**. They never go to Supabase.

## How the locking works (envelope encryption)
Think of a bank's safe-deposit room:
1. Every secret gets **its own new random key** (a 256-bit AES-GCM key) and is locked with it.
2. That small key is then locked with the **master key** from your `.env`.
3. The file stores only the two locked things. Without the master key, nothing opens.

Extra protections:
- **Tamper detection:** AES-GCM notices any changed byte and refuses to decrypt.
- **Name binding:** each secret is tied to its name (e.g. `oauth:google`). Copying the bytes under another name doesn't work.
- The same secret encrypted twice looks completely different (random keys and nonces).

## What was built
| File | In simple terms |
|---|---|
| `app/secrets.py` | `encrypt`/`decrypt` functions + `SecretStore` with `put`, `get`, `delete`, `values_of_kind`. The file lives at `SECRETS_DB_PATH` (`/secrets/secrets.db` on the Docker volume). |
| `tests/test_secrets.py` | 9 tests |

`values_of_kind("site")` exists for the outbound leak check (T-14): before sending a reply, we check it doesn't contain one of your saved passwords.

## Tests (9, all passing)
Round trip · missing → None · overwrite + delete · **the raw file never contains the plaintext** · wrong master key fails · flipped byte fails · row copied to another name fails · same value encrypts differently · values_of_kind.

## Things to know
- **Back up your `MASTER_KEY`** (password manager). If you lose it, the stored secrets are unrecoverable. That's by design.
- The file is named `secrets.py`, like Python's built-in `secrets` module. That's fine because we always run code with `python -m …` from the project folder.

## Credentials needed?
Only the `MASTER_KEY` in `.env` (generate it with the command in the README).

## Next
**T-05:** the Telegram client (sending messages, buttons, formatting).
