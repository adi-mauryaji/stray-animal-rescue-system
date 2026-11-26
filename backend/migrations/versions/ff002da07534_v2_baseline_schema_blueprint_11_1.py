"""v2 baseline schema (blueprint 11.1)

The whole v2 schema in one revision: there is no v1 data anywhere to migrate
forward (vault decision 014), so this is the first revision of a fresh
history. The SQL is the reviewed DDL of blueprint 11.1, copied statement by
statement — one op.execute() per statement, because asyncpg refuses several
commands in one call. The only addition is the updated_at trigger on each
table that has the column (the blueprint shows one and says "repeat").

Needs the custom image of Section 24.1: PostGIS 3.6, pgvector and
pg_stat_statements in shared_preload_libraries.

Revision ID: ff002da07534
Revises:
Create Date: 2026-11-25 03:10:32.838828

"""

from collections.abc import Sequence

from alembic import op

revision: str = "ff002da07534"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        r"""
        create extension if not exists postgis
        """
    )

    op.execute(
        r"""
        create extension if not exists vector  -- pgvector (image embeddings)
        """
    )

    op.execute(
        r"""
        create extension if not exists citext  -- case-insensitive email
        """
    )

    op.execute(
        r"""
        create extension if not exists pg_stat_statements  -- needs shared_preload_libraries (Section 24)
        """
    )

    op.execute(
        r"""
        create schema if not exists core
        """
    )

    op.execute(
        r"""
        create schema if not exists identity
        """
    )

    op.execute(
        r"""
        create schema if not exists org
        """
    )

    op.execute(
        r"""
        create schema if not exists responder
        """
    )

    op.execute(
        r"""
        create schema if not exists intake
        """
    )

    op.execute(
        r"""
        create schema if not exists dispatch
        """
    )

    op.execute(
        r"""
        create schema if not exists notify
        """
    )

    op.execute(
        r"""
        create schema if not exists platform
        """
    )

    op.execute(
        r"""
        create function core.touch_updated_at() returns trigger language plpgsql as $$
        begin new.updated_at := now(); return new; end $$
        """
    )

    op.execute(
        r"""
        -- ===================== core =====================
        create table core.regions (
          id               text primary key,                    -- stable shard key, e.g. 'in-ka-bengaluru'
          name             text not null,
          timezone         text not null default 'Asia/Kolkata',
          boundary         geography(MultiPolygon, 4326) not null,
          is_active        boolean not null default true,
          dispatch_config  jsonb not null default '{}'::jsonb,  -- overrides of code defaults (radii, TTLs, weights)
          created_at       timestamptz not null default now()
        )
        """
    )

    op.execute(
        r"""
        create index regions_boundary_gist on core.regions using gist (boundary)
        """
    )

    op.execute(
        r"""
        -- ===================== identity =====================
        create table identity.users (
          id                 uuid primary key default uuidv7(),
          display_name       text not null,
          email              citext unique,
          phone_e164         text unique check (phone_e164 ~ '^\+[1-9][0-9]{7,14}$'),
          platform_role      text not null default 'member' check (platform_role in ('member','platform_admin')),
          status             text not null default 'active' check (status in ('active','suspended','deleted')),
          locale             text not null default 'en',
          email_verified_at  timestamptz,
          phone_verified_at  timestamptz,
          totp_secret_enc    bytea,                              -- required for platform_admin (Section 14)
          created_at         timestamptz not null default now(),
          updated_at         timestamptz not null default now(),
          check (email is not null or phone_e164 is not null)
        )
        """
    )

    op.execute(
        r"""
        create table identity.auth_identities (               -- many login methods per user (password, Google, email OTP)
          id                uuid primary key default uuidv7(),
          user_id           uuid not null references identity.users(id) on delete cascade,
          provider          text not null check (provider in ('password','google','email_otp')),
          provider_subject  text not null,                       -- email, or Google 'sub' claim
          password_hash     text,                                -- argon2id, only for provider = 'password'
          created_at        timestamptz not null default now(),
          last_used_at      timestamptz,
          unique (provider, provider_subject),
          check ((provider = 'password') = (password_hash is not null))
        )
        """
    )

    op.execute(
        r"""
        create index auth_identities_user_idx on identity.auth_identities (user_id)
        """
    )

    op.execute(
        r"""
        create table identity.sessions (                       -- opaque server-side sessions (Section 14)
          id            uuid primary key default uuidv7(),
          user_id       uuid not null references identity.users(id) on delete cascade,
          token_hash    bytea not null unique,                   -- sha256 of the cookie token; raw token never stored
          created_at    timestamptz not null default now(),
          last_seen_at  timestamptz not null default now(),
          expires_at    timestamptz not null,
          revoked_at    timestamptz,
          ip            inet,
          user_agent    text
        )
        """
    )

    op.execute(
        r"""
        create index sessions_user_live_idx on identity.sessions (user_id) where revoked_at is null
        """
    )

    op.execute(
        r"""
        -- ===================== org =====================
        create table org.organizations (
          id                uuid primary key default uuidv7(),
          region_id         text not null references core.regions(id),
          name              text not null,
          org_type          text not null check (org_type in ('ngo','shelter','clinic','municipal')),
          registration_no   text,
          base_location     geography(Point, 4326) not null,
          service_area      geography(MultiPolygon, 4326),       -- null → radius around base (region config)
          shelter_capacity  integer check (shelter_capacity >= 0),
          accepts_species   text[] not null default '{}',
          verified_at       timestamptz,
          verified_by       uuid references identity.users(id),
          created_at        timestamptz not null default now(),
          updated_at        timestamptz not null default now()
        )
        """
    )

    op.execute(
        r"""
        create index organizations_region_idx   on org.organizations (region_id)
        """
    )

    op.execute(
        r"""
        create index organizations_base_gist    on org.organizations using gist (base_location)
        """
    )

    op.execute(
        r"""
        create index organizations_area_gist    on org.organizations using gist (service_area)
        """
    )

    op.execute(
        r"""
        create index organizations_verifier_idx on org.organizations (verified_by)
        """
    )

    op.execute(
        r"""
        create table org.memberships (                         -- links NGO/shelter/clinic staff to their org (missing in v1)
          organization_id  uuid not null references org.organizations(id) on delete cascade,
          user_id          uuid not null references identity.users(id) on delete cascade,
          role             text not null check (role in ('org_admin','dispatcher','member')),
          status           text not null default 'active' check (status in ('invited','active','removed')),
          created_at       timestamptz not null default now(),
          primary key (organization_id, user_id)
        )
        """
    )

    op.execute(
        r"""
        create index memberships_user_idx on org.memberships (user_id)
        """
    )

    op.execute(
        r"""
        -- ===================== responder =====================
        create table responder.responders (                    -- ONE table for volunteers, vets, org staff (v1 had two)
          id                    uuid primary key default uuidv7(),
          user_id               uuid not null unique references identity.users(id) on delete cascade,
          organization_id       uuid references org.organizations(id) on delete set null,
          home_region_id        text not null references core.regions(id),
          responder_type        text not null check (responder_type in ('volunteer','veterinarian','org_staff')),
          vehicle_type          text not null default 'none'
                                  check (vehicle_type in ('none','two_wheeler','car','van','ambulance')),
          capabilities          text[] not null default '{}',    -- controlled vocabulary in code (Section 16.1)
          max_concurrent_cases  smallint not null default 1 check (max_concurrent_cases between 1 and 10),
          verification_status   text not null default 'pending'
                                  check (verification_status in ('pending','verified','rejected','suspended')),
          verified_by           uuid references identity.users(id),
          verified_at           timestamptz,
          license_no            text,
          rel_alpha             double precision not null default 2.0,   -- Beta posterior (Section 6.6), not a bare score
          rel_beta              double precision not null default 2.0,
          created_at            timestamptz not null default now(),
          updated_at            timestamptz not null default now(),
          check (responder_type <> 'veterinarian' or license_no is not null)
        )
        """
    )

    op.execute(
        r"""
        create index responders_org_idx          on responder.responders (organization_id)
        """
    )

    op.execute(
        r"""
        create index responders_region_idx       on responder.responders (home_region_id)
        """
    )

    op.execute(
        r"""
        create index responders_verifier_idx     on responder.responders (verified_by)
        """
    )

    op.execute(
        r"""
        create index responders_capabilities_gin on responder.responders using gin (capabilities)
        """
    )

    op.execute(
        r"""
        create table responder.presence (                      -- hot, narrow, frequently updated; separate from the profile
          responder_id   uuid primary key references responder.responders(id) on delete cascade,
          region_id      text not null references core.regions(id),
          status         text not null default 'offline' check (status in ('offline','available','busy','paused')),
          location       geography(Point, 4326),
          accuracy_m     real,
          location_at    timestamptz,
          active_cases   smallint not null default 0 check (active_cases >= 0),
          updated_at     timestamptz not null default now()
        )
        """
    )

    op.execute(
        r"""
        -- Partial GiST: only rows that can actually be matched are indexed (v1's partial index forgot USING GIST).
        create index presence_available_gist   on responder.presence using gist (location) where status = 'available'
        """
    )

    op.execute(
        r"""
        create index presence_region_status_idx on responder.presence (region_id, status)
        """
    )

    op.execute(
        r"""
        alter table responder.presence set (autovacuum_vacuum_scale_factor = 0.02, autovacuum_analyze_scale_factor = 0.02)
        """
    )

    op.execute(
        r"""
        -- ===================== intake =====================
        create table intake.incidents (                        -- one real-world event; many reports can point to it
          id                     uuid primary key default uuidv7(),
          region_id              text not null references core.regions(id),
          public_ref             text not null unique,          -- human code, e.g. BLR-7K3Q
          status                 text not null default 'new' check (status in
                                   ('new','dispatching','assigned','en_route','on_scene',
                                    'resolved','unresolved','cancelled','merged')),
          needs_human            boolean not null default false, -- escalated after last wave, or low-confidence triage
          merged_into_id         uuid references intake.incidents(id),
          species                text not null default 'unknown',
          severity               text check (severity in ('minor','moderate','severe','critical')),
          severity_source        text check (severity_source in ('citizen_triage','rules','ai','human')),
          severity_confidence    real check (severity_confidence between 0 and 1),
          base_priority          real not null default 0,       -- time-independent part; urgency added at read time (6.1)
          required_capabilities  text[] not null default '{}',
          location               geography(Point, 4326) not null,
          location_accuracy_m    real,
          h3_r9                  bigint not null,               -- H3 cell (~0.1 km²): aggregation, privacy, sharding
          address_text           text,
          created_at             timestamptz not null default now(),
          updated_at             timestamptz not null default now(),
          closed_at              timestamptz,
          version                integer not null default 1     -- optimistic concurrency (ETag / If-Match) for console edits
        )
        """
    )

    op.execute(
        r"""
        create index incidents_open_idx on intake.incidents (region_id, status, created_at)
          where status in ('new','dispatching','assigned','en_route','on_scene')
        """
    )

    op.execute(
        r"""
        create index incidents_location_gist on intake.incidents using gist (location)
        """
    )

    op.execute(
        r"""
        create index incidents_created_brin  on intake.incidents using brin (created_at)
        """
    )

    op.execute(
        r"""
        create index incidents_merged_idx    on intake.incidents (merged_into_id) where merged_into_id is not null
        """
    )

    op.execute(
        r"""
        create table intake.reports (
          id                    uuid primary key,               -- generated by the client = idempotency key for retries
          incident_id           uuid not null references intake.incidents(id),
          region_id             text not null references core.regions(id),
          reporter_user_id      uuid references identity.users(id),   -- null for guest reports
          tracking_token_hash   bytea not null unique,         -- capability URL for guests (Section 14.1)
          reporter_contact      text,                           -- optional; purged by retention job (Section 20.5)
          channel               text not null default 'web' check (channel in ('web','telegram','console')),
          species_reported      text not null default 'unknown',
          description           text check (length(description) <= 2000),
          triage                jsonb not null default '{}'::jsonb,   -- {bleeding, can_walk, conscious, trapped, on_road, young}
          location              geography(Point, 4326) not null,
          location_source       text not null check (location_source in ('gps','exif','manual_pin')),
          location_accuracy_m   real,
          client_created_at     timestamptz,
          created_at            timestamptz not null default now()
        )
        """
    )

    op.execute(
        r"""
        create index reports_incident_idx  on intake.reports (incident_id)
        """
    )

    op.execute(
        r"""
        create index reports_region_idx    on intake.reports (region_id)
        """
    )

    op.execute(
        r"""
        create index reports_reporter_idx  on intake.reports (reporter_user_id) where reporter_user_id is not null
        """
    )

    op.execute(
        r"""
        create index reports_location_gist on intake.reports using gist (location)
        """
    )

    op.execute(
        r"""
        create table intake.media (
          id                uuid primary key default uuidv7(),
          report_id         uuid references intake.reports(id) on delete cascade,  -- null until the report is submitted
          uploader_key      bytea not null,                       -- hash of session/device; prevents attaching others' uploads
          object_key        text not null unique,                 -- storage key, never a public URL (URLs are signed on read)
          content_type      text not null check (content_type in ('image/jpeg','image/png','image/webp')),
          bytes             integer not null check (bytes between 1 and 10485760),
          width             integer,
          height            integer,
          sha256            bytea,
          phash             bigint,                               -- 64-bit perceptual hash
          embedding         vector(768),                          -- dimension fixed by the chosen image model (ADR)
          quality_score     real,
          ai_species        text,
          ai_species_conf   real,
          ai_model_version  text,                                 -- which model produced the AI fields (reproducibility)
          status            text not null default 'pending' check (status in ('pending','ready','rejected')),
          created_at        timestamptz not null default now()
        )
        """
    )

    op.execute(
        r"""
        create index media_report_idx on intake.media (report_id)
        """
    )

    op.execute(
        r"""
        -- ===================== dispatch =====================
        create table dispatch.dispatches (                     -- one dispatch run per incident at a time
          id           uuid primary key default uuidv7(),
          incident_id  uuid not null references intake.incidents(id),
          region_id    text not null references core.regions(id),
          status       text not null default 'active' check (status in ('active','accepted','exhausted','cancelled')),
          wave         smallint not null default 0,
          radius_m     integer not null,
          policy       jsonb not null,                           -- frozen weights/radii/TTLs used → reproducible + ablation-ready
          started_at   timestamptz not null default now(),
          ended_at     timestamptz
        )
        """
    )

    op.execute(
        r"""
        create unique index dispatches_one_active_per_incident on dispatch.dispatches (incident_id) where status = 'active'
        """
    )

    op.execute(
        r"""
        create index dispatches_incident_idx       on dispatch.dispatches (incident_id)
        """
    )

    op.execute(
        r"""
        create index dispatches_region_active_idx  on dispatch.dispatches (region_id) where status = 'active'
        """
    )

    op.execute(
        r"""
        create table dispatch.offers (
          id               uuid primary key default uuidv7(),
          dispatch_id      uuid not null references dispatch.dispatches(id) on delete cascade,
          incident_id      uuid not null references intake.incidents(id),
          responder_id     uuid not null references responder.responders(id),
          wave             smallint not null,
          rank             smallint not null,
          score            real not null,
          score_breakdown  jsonb not null,                       -- every factor value: explainability + research data
          distance_m       integer not null,
          eta_s            integer,
          status           text not null default 'pending'
                             check (status in ('pending','accepted','declined','expired','withdrawn')),
          offered_at       timestamptz not null default now(),
          expires_at       timestamptz not null,
          responded_at     timestamptz,
          decline_reason   text,
          unique (dispatch_id, responder_id)
        )
        """
    )

    op.execute(
        r"""
        create index offers_responder_pending_idx on dispatch.offers (responder_id) where status = 'pending'
        """
    )

    op.execute(
        r"""
        create index offers_expiry_idx            on dispatch.offers (expires_at)   where status = 'pending'
        """
    )

    op.execute(
        r"""
        create index offers_incident_idx          on dispatch.offers (incident_id)
        """
    )

    op.execute(
        r"""
        create table dispatch.assignments (
          id            uuid primary key default uuidv7(),
          incident_id   uuid not null references intake.incidents(id),
          responder_id  uuid not null references responder.responders(id),
          offer_id      uuid references dispatch.offers(id),     -- null for manual assignment by a dispatcher
          assigned_by   uuid references identity.users(id),
          status        text not null default 'active'
                          check (status in ('active','en_route','on_scene','completed','released','no_show')),
          outcome       text check (outcome in ('treated_on_site','to_clinic','to_shelter','not_found',
                                                'deceased','false_report','other')),
          assigned_at   timestamptz not null default now(),
          en_route_at   timestamptz,
          arrived_at    timestamptz,
          completed_at  timestamptz,
          notes         text
        )
        """
    )

    op.execute(
        r"""
        -- THE double-assignment guard, enforced by the database, not by application timing:
        create unique index assignments_one_live_per_incident on dispatch.assignments (incident_id)
          where status in ('active','en_route','on_scene')
        """
    )

    op.execute(
        r"""
        create index assignments_responder_live_idx on dispatch.assignments (responder_id)
          where status in ('active','en_route','on_scene')
        """
    )

    op.execute(
        r"""
        create index assignments_offer_idx       on dispatch.assignments (offer_id)
        """
    )

    op.execute(
        r"""
        create index assignments_assigned_by_idx on dispatch.assignments (assigned_by)
        """
    )

    op.execute(
        r"""
        -- ===================== notify =====================
        create table notify.push_subscriptions (
          id          uuid primary key default uuidv7(),
          user_id     uuid not null references identity.users(id) on delete cascade,
          endpoint    text not null unique,
          p256dh      text not null,
          auth        text not null,
          created_at  timestamptz not null default now(),
          last_ok_at  timestamptz,
          revoked_at  timestamptz
        )
        """
    )

    op.execute(
        r"""
        create index push_subscriptions_user_idx on notify.push_subscriptions (user_id) where revoked_at is null
        """
    )

    op.execute(
        r"""
        create table notify.telegram_links (
          user_id    uuid primary key references identity.users(id) on delete cascade,
          chat_id    bigint not null unique,
          linked_at  timestamptz not null default now()
        )
        """
    )

    op.execute(
        r"""
        create table notify.deliveries (                       -- a message on a channel; NOT the same thing as an offer
          id                 uuid primary key default uuidv7(),
          recipient_user_id  uuid not null references identity.users(id),
          offer_id           uuid references dispatch.offers(id),
          incident_id        uuid references intake.incidents(id),
          channel            text not null check (channel in ('web_push','telegram','email','sms')),
          template           text not null,
          status             text not null default 'queued' check (status in ('queued','sent','failed','dead')),
          attempts           smallint not null default 0,
          provider_ref       text,
          last_error         text,
          created_at         timestamptz not null default now(),
          sent_at            timestamptz,
          unique (offer_id, channel)                           -- idempotency: one delivery per offer per channel
        )
        """
    )

    op.execute(
        r"""
        create index deliveries_recipient_idx on notify.deliveries (recipient_user_id, created_at desc)
        """
    )

    op.execute(
        r"""
        create index deliveries_incident_idx  on notify.deliveries (incident_id)
        """
    )

    op.execute(
        r"""
        create index deliveries_problem_idx   on notify.deliveries (created_at) where status in ('failed','dead')
        """
    )

    op.execute(
        r"""
        -- ===================== platform =====================
        create table platform.outbox (
          id            bigint generated always as identity primary key,
          topic         text not null,                           -- 'report.created', 'offer.accepted', ...
          key           text not null,                           -- ordering key (incident id) → Kafka/NATS key later
          payload       jsonb not null,
          created_at    timestamptz not null default now(),
          published_at  timestamptz
        )
        """
    )

    op.execute(
        r"""
        create index outbox_unpublished_idx on platform.outbox (id) where published_at is null
        """
    )

    op.execute(
        r"""
        -- Append-only, partitioned from day 1 (retrofitting partitioning later is painful).
        create table platform.incident_events (                -- was rescue_timeline in v1
          id             uuid not null default uuidv7(),
          incident_id    uuid not null,                          -- no FK: partition-friendly and survives archival
          region_id      text not null,
          event_type     text not null,
          actor_kind     text not null check (actor_kind in ('user','system','ai')),
          actor_user_id  uuid,
          payload        jsonb not null default '{}'::jsonb,
          occurred_at    timestamptz not null default now(),
          primary key (id, occurred_at)
        ) partition by range (occurred_at)
        """
    )

    op.execute(
        r"""
        create table platform.incident_events_default partition of platform.incident_events default
        """
    )

    op.execute(
        r"""
        create index incident_events_incident_idx on platform.incident_events (incident_id, occurred_at)
        """
    )

    op.execute(
        r"""
        create table platform.audit_log (
          id             uuid not null default uuidv7(),
          actor_user_id  uuid,
          action         text not null,                          -- 'assignment.override', 'responder.verify', 'data.export', ...
          entity_type    text not null,
          entity_id      uuid,
          before_state   jsonb,
          after_state    jsonb,
          ip             inet,
          request_id     text,
          created_at     timestamptz not null default now(),
          primary key (id, created_at)
        ) partition by range (created_at)
        """
    )

    op.execute(
        r"""
        create table platform.audit_log_default partition of platform.audit_log default
        """
    )

    op.execute(
        r"""
        create index audit_log_entity_idx on platform.audit_log (entity_type, entity_id)
        """
    )

    op.execute(
        r"""
        create index audit_log_actor_idx  on platform.audit_log (actor_user_id, created_at)
        """
    )

    op.execute(
        r"""
        -- updated_at triggers: one per table that has an updated_at column
        create trigger users_touch before update on identity.users
          for each row execute function core.touch_updated_at()
        """
    )

    op.execute(
        r"""
        create trigger organizations_touch before update on org.organizations
          for each row execute function core.touch_updated_at()
        """
    )

    op.execute(
        r"""
        create trigger responders_touch before update on responder.responders
          for each row execute function core.touch_updated_at()
        """
    )

    op.execute(
        r"""
        create trigger presence_touch before update on responder.presence
          for each row execute function core.touch_updated_at()
        """
    )

    op.execute(
        r"""
        create trigger incidents_touch before update on intake.incidents
          for each row execute function core.touch_updated_at()
        """
    )


def downgrade() -> None:
    """Drop what this revision created: the module schemas and their contents."""
    op.execute("drop schema if exists notify cascade")
    op.execute("drop schema if exists dispatch cascade")
    op.execute("drop schema if exists intake cascade")
    op.execute("drop schema if exists responder cascade")
    op.execute("drop schema if exists org cascade")
    op.execute("drop schema if exists identity cascade")
    op.execute("drop schema if exists core cascade")
    op.execute("drop schema if exists platform cascade")
    # citext and vector arrived with this revision and nothing else uses them.
    op.execute("drop extension if exists vector")
    op.execute("drop extension if exists citext")
    # postgis stays: the image's init script creates it together with
    # postgis_topology and postgis_tiger_geocoder, which depend on it, so
    # dropping it here fails. pg_stat_statements stays too — it is a
    # server-level view, not part of this schema.
