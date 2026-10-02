# T-36: Backups and wipe — what we have done

**Status:** done ✅ (backup tested end to end)

## In one sentence
One command **backs up** everything you'd need after a disk failure, and one command **deletes all your data**.

## Backup: `sh scripts/backup.sh` (Git Bash or WSL, from the project folder)
Creates `backup/<date>/` with:
| File | Contains |
|---|---|
| `app.sql.gz` | The Supabase `app` schema: messages, memory, approvals, audit, … |
| `secrets.tgz` | The encrypted secrets file. **Useless without your `MASTER_KEY`**: keep that in your password manager. |
| `temporal-data.tgz` | Temporal's state, **including your scheduled tasks** |

`pg_dump` runs inside a Postgres container, so you don't need to install anything. The browser profile isn't backed up; you'd just log into sites again.

**Tested:** a backup of the test database produced all 9 tables plus both volume archives.

## Wipe: delete everything
```sh
docker compose run --rm worker-agent python -m scripts.wipe   # asks you to type WIPE
docker compose down -v                                        # removes local volumes
```
In order: **revoke Google's access at Google** → delete the local tokens → drop the Supabase schema → (`down -v`) delete secrets, browser profile and Temporal state. Anything other than exactly `WIPE` cancels (tested).

## Restore (if you ever need it)
1. Database: `gunzip -c backup/<date>/app.sql.gz | psql "$DATABASE_URL"`
2. Volumes: `docker compose down`, then for each archive:
   `docker run --rm -v extinct_secrets:/v -v "$PWD/backup/<date>:/b" alpine tar xzf /b/secrets.tgz -C /v` (same for `temporal-data`)
3. `docker compose up -d`, with the **same `MASTER_KEY`** in `.env`.

## Next
**T-37:** scenario evaluation.
