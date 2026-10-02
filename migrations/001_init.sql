-- App data for Mini-Instinct (Supabase / any Postgres 15+).
-- Single user, so there are no user_id columns. Scheduled tasks live in Temporal, not here.
-- Keep schema "app" OUT of Supabase's exposed API schemas (Settings -> Data API).

CREATE SCHEMA IF NOT EXISTS app;
SET search_path = app;

-- Every Telegram message in or out (and button taps).
CREATE TABLE messages (
    id            bigserial PRIMARY KEY,
    direction     text NOT NULL CHECK (direction IN ('in', 'out')),
    tg_update_id  bigint UNIQUE,                       -- dedupe for inbound updates
    tg_message_id bigint,
    kind          text NOT NULL DEFAULT 'text',        -- text / button / photo / other
    body          text NOT NULL DEFAULT '',
    sent_at       timestamptz NOT NULL DEFAULT now(),
    dispatched    boolean NOT NULL DEFAULT false,      -- outbox flag: handed to Temporal?
    consumed_by   text,                                -- set when a browser task used it as input
    turn_id       uuid,
    tsv           tsvector GENERATED ALWAYS AS (to_tsvector('simple', body)) STORED
);
CREATE INDEX messages_sent_at ON messages (sent_at DESC);
CREATE INDEX messages_undispatched ON messages (id) WHERE direction = 'in' AND NOT dispatched;
CREATE INDEX messages_tsv ON messages USING gin (tsv);

-- One agent run (main conversation turn or a browser sub-agent run).
CREATE TABLE agent_turns (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    kind           text NOT NULL DEFAULT 'main',       -- main / browser
    parent_turn_id uuid,
    trigger        text NOT NULL DEFAULT 'message',    -- message / task_due / takeover_done / ...
    status         text NOT NULL DEFAULT 'running',    -- running / done / stopped / failed
    model          text,
    prompt_version text,
    messages       jsonb NOT NULL DEFAULT '[]',        -- append-only within a turn
    tool_menu      text[] NOT NULL DEFAULT '{}',       -- frozen at turn start
    steps          int NOT NULL DEFAULT 0,
    started_at     timestamptz NOT NULL DEFAULT now(),
    ended_at       timestamptz
);

-- One row per executed tool call. The primary key makes retries idempotent.
CREATE TABLE tool_results (
    turn_id      uuid NOT NULL,
    tool_call_id text NOT NULL,
    tool         text NOT NULL,
    content      jsonb NOT NULL,
    is_error     boolean NOT NULL DEFAULT false,
    created_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (turn_id, tool_call_id)
);

CREATE TABLE memory_facts (
    id                bigserial PRIMARY KEY,
    kind              text NOT NULL DEFAULT 'other',   -- preference / person / place / other
    content           text NOT NULL,
    source_message_id bigint,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    tsv               tsvector GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED
);
CREATE UNIQUE INDEX memory_facts_content ON memory_facts (lower(btrim(content)));
CREATE INDEX memory_facts_tsv ON memory_facts USING gin (tsv);

-- Pending button actions: approvals for risky tools, and browser takeovers.
CREATE TABLE approvals (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    turn_id       uuid,
    tool          text NOT NULL,                       -- tool name, or 'takeover'
    input         jsonb NOT NULL DEFAULT '{}',
    summary       text NOT NULL DEFAULT '',            -- rendered by code, never by the model
    status        text NOT NULL DEFAULT 'pending',     -- pending/executing/executed/rejected/failed/done
    tg_message_id bigint,                              -- the button message, edited after a tap
    result        jsonb,
    expires_at    timestamptz NOT NULL,
    decided_at    timestamptz,
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX approvals_status ON approvals (status);

-- Append-only record of every guard decision and execution.
CREATE TABLE audit_log (
    id         bigserial PRIMARY KEY,
    turn_id    uuid,
    actor      text NOT NULL DEFAULT 'agent',          -- agent / user / system
    tool       text NOT NULL,
    tier       text,
    decision   text NOT NULL,                          -- allowed/denied/needs_approval/executed/failed/blocked
    detail     jsonb NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX audit_log_tool_time ON audit_log (tool, decision, created_at);

CREATE TABLE connections (
    provider   text PRIMARY KEY,                        -- google / ...
    status     text NOT NULL,                           -- connected / needs_reauth / revoked
    scopes     text[] NOT NULL DEFAULT '{}',
    meta       jsonb NOT NULL DEFAULT '{}',
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- Every model request: daily free-tier budget + usage report.
CREATE TABLE llm_calls (
    id                bigserial PRIMARY KEY,
    at                timestamptz NOT NULL DEFAULT now(),
    kind              text NOT NULL,                    -- main / browser / probe
    model             text NOT NULL,
    status            text NOT NULL DEFAULT 'ok',       -- ok / error
    prompt_tokens     int,
    completion_tokens int,
    cost              numeric
);
CREATE INDEX llm_calls_at ON llm_calls (at);

-- Defense in depth: RLS on, no policies. Only the owner role (our server connection) can read/write;
-- Supabase's anon/authenticated API roles get nothing even if the schema were exposed by mistake.
ALTER TABLE messages     ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_turns  ENABLE ROW LEVEL SECURITY;
ALTER TABLE tool_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE memory_facts ENABLE ROW LEVEL SECURITY;
ALTER TABLE approvals    ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log    ENABLE ROW LEVEL SECURITY;
ALTER TABLE connections  ENABLE ROW LEVEL SECURITY;
ALTER TABLE llm_calls    ENABLE ROW LEVEL SECURITY;
