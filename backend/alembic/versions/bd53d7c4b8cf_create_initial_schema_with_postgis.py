"""create initial schema with postgis

Revision ID: bd53d7c4b8cf
Revises: 
Create Date: 2026-07-18 19:46:01.645979

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bd53d7c4b8cf'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Extensions
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')

    # Parent tables

    op.execute("""
        CREATE TABLE users (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            email VARCHAR(255) UNIQUE NOT NULL,
            phone VARCHAR(20) UNIQUE,
            password_hash VARCHAR(255) NOT NULL,
            full_name VARCHAR(255) NOT NULL,
            role VARCHAR(20) NOT NULL CHECK (role IN
                ('citizen','volunteer','veterinarian','ngo_admin','shelter_admin','admin')),
            is_active BOOLEAN DEFAULT TRUE,
            is_verified BOOLEAN DEFAULT FALSE,
            fcm_token TEXT,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        );
    """)
    op.execute("CREATE INDEX idx_users_role ON users(role);")
    op.execute("CREATE INDEX idx_users_email ON users(email);")

    op.execute("""CREATE TABLE organizations (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            VARCHAR(255) NOT NULL,
    org_type        VARCHAR(20) NOT NULL CHECK (org_type IN ('ngo','shelter','clinic')),
    registration_no VARCHAR(100),
    contact_email   VARCHAR(255),
    contact_phone   VARCHAR(20),
    location        GEOGRAPHY(Point, 4326) NOT NULL,
    address_text    TEXT,
    capacity        INTEGER DEFAULT 0,
    is_verified     BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_org_location ON organizations USING GIST(location);""")
    
    op.execute("""CREATE TABLE veterinarians (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    organization_id     UUID REFERENCES organizations(id) ON DELETE SET NULL,
    license_no          VARCHAR(100) NOT NULL,
    specialization      VARCHAR(100),
    years_experience    INTEGER DEFAULT 0,
    current_location    GEOGRAPHY(Point, 4326),
    is_on_duty          BOOLEAN DEFAULT FALSE,
    active_case_count   INTEGER DEFAULT 0,
    reliability_score   NUMERIC(4,3) DEFAULT 0.500,
    created_at          TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_vet_location ON veterinarians USING GIST(current_location);
CREATE INDEX idx_vet_on_duty ON veterinarians(is_on_duty);""")
    
    op.execute("""CREATE TABLE volunteers (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    organization_id     UUID REFERENCES organizations(id) ON DELETE SET NULL,
    vehicle_type        VARCHAR(30) CHECK (vehicle_type IN ('two_wheeler','car','van','none')),
    capability_tags     TEXT[] DEFAULT '{}',
    current_location    GEOGRAPHY(Point, 4326),
    is_on_duty          BOOLEAN DEFAULT FALSE,
    active_case_count   INTEGER DEFAULT 0,
    reliability_score   NUMERIC(4,3) DEFAULT 0.500,
    total_rescues       INTEGER DEFAULT 0,
    created_at          TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_volunteer_location ON volunteers USING GIST(current_location);
CREATE INDEX idx_volunteer_on_duty ON volunteers(is_on_duty);
CREATE INDEX idx_volunteer_capability_tags ON volunteers USING GIN(capability_tags);""")
    
    op.execute("""CREATE TABLE shelters (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id     UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    location            GEOGRAPHY(Point, 4326) NOT NULL,
    total_capacity      INTEGER NOT NULL DEFAULT 0,
    current_occupancy   INTEGER NOT NULL DEFAULT 0,
    accepts_species     TEXT[] DEFAULT '{}',
    created_at          TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_shelter_location ON shelters USING GIST(location);""")
    
    op.execute("""CREATE TABLE animals (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    species         VARCHAR(50),
    estimated_breed VARCHAR(100),
    estimated_age   VARCHAR(30),
    sex             VARCHAR(10) CHECK (sex IN ('male','female','unknown')),
    distinguishing_marks TEXT,
    is_chipped      BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT now()
);""")
    
    op.execute("""CREATE TABLE locations (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    point           GEOGRAPHY(Point, 4326) NOT NULL,
    address_text    TEXT,
    city            VARCHAR(100),
    state           VARCHAR(100),
    postal_code     VARCHAR(20),
    accuracy_meters NUMERIC(6,2),
    source          VARCHAR(20) CHECK (source IN ('gps','manual_pin','exif')),
    created_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_locations_point ON locations USING GIST(point);""")
    
    op.execute("""CREATE TABLE reports (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    reporter_id         UUID NOT NULL REFERENCES users(id),
    animal_id           UUID REFERENCES animals(id),
    location_id         UUID NOT NULL REFERENCES locations(id),
    description         TEXT,
    severity_label      VARCHAR(20) CHECK (severity_label IN
                          ('minor','moderate','severe','critical','unclear')),
    severity_confidence NUMERIC(4,3),
    priority_score      NUMERIC(6,3) DEFAULT 0,
    status              VARCHAR(30) NOT NULL DEFAULT 'submitted' CHECK (status IN
                          ('submitted','triaged','matching','assigned','en_route',
                           'in_progress','resolved','closed','cancelled')),
    is_duplicate_of     UUID REFERENCES reports(id),
    created_at          TIMESTAMPTZ DEFAULT now(),
    updated_at          TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_reports_status ON reports(status);
CREATE INDEX idx_reports_priority ON reports(priority_score DESC);
CREATE INDEX idx_reports_created_at ON reports(created_at);""")
    
    op.execute("""CREATE TABLE images (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    report_id       UUID NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
    storage_url     TEXT NOT NULL,
    quality_score   NUMERIC(4,3),
    ai_detected_species VARCHAR(50),
    ai_confidence   NUMERIC(4,3),
    uploaded_at     TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_images_report ON images(report_id);""")
    
    op.execute("""CREATE TABLE emergency_requests (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    report_id           UUID NOT NULL UNIQUE REFERENCES reports(id) ON DELETE CASCADE,
    current_radius_km   NUMERIC(5,2) DEFAULT 2.0,
    expansion_count     INTEGER DEFAULT 0,
    assigned_responder_id UUID,
    assigned_responder_type VARCHAR(20) CHECK (assigned_responder_type IN
                              ('volunteer','veterinarian','ngo','shelter')),
    matching_attempts   INTEGER DEFAULT 0,
    created_at          TIMESTAMPTZ DEFAULT now(),
    resolved_at         TIMESTAMPTZ
);
CREATE INDEX idx_er_report ON emergency_requests(report_id);""")
    
    op.execute("""CREATE TABLE notifications (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    emergency_request_id UUID NOT NULL REFERENCES emergency_requests(id) ON DELETE CASCADE,
    recipient_user_id   UUID NOT NULL REFERENCES users(id),
    channel             VARCHAR(20) CHECK (channel IN ('push','email','sms')),
    status              VARCHAR(20) DEFAULT 'queued' CHECK (status IN
                          ('queued','sent','delivered','acked','declined','timed_out','failed')),
    sent_at             TIMESTAMPTZ,
    responded_at        TIMESTAMPTZ,
    retry_count         INTEGER DEFAULT 0,
    created_at          TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_notif_er ON notifications(emergency_request_id);
CREATE INDEX idx_notif_status ON notifications(status);""")
    
    op.execute("""CREATE TABLE rescue_timeline (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    report_id       UUID NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
    event_type      VARCHAR(40) NOT NULL,
    actor_user_id   UUID REFERENCES users(id),
    metadata        JSONB,
    occurred_at     TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_timeline_report ON rescue_timeline(report_id);
CREATE INDEX idx_timeline_event_type ON rescue_timeline(event_type);""")
    
    op.execute("""CREATE TABLE response_history (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    report_id           UUID NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
    responder_user_id   UUID NOT NULL REFERENCES users(id),
    responder_type      VARCHAR(20) CHECK (responder_type IN ('volunteer','veterinarian')),
    was_assigned        BOOLEAN DEFAULT FALSE,
    accepted            BOOLEAN,
    arrived             BOOLEAN,
    outcome             VARCHAR(20) CHECK (outcome IN
                          ('success','partial','failed','no_show','unknown')),
    response_time_seconds INTEGER,
    created_at          TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_resp_hist_responder ON response_history(responder_user_id);
CREATE INDEX idx_resp_hist_outcome ON response_history(outcome);""")
    
    op.execute("""CREATE TABLE audit_logs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    actor_user_id   UUID REFERENCES users(id),
    action          VARCHAR(100) NOT NULL,
    entity_type     VARCHAR(50),
    entity_id       UUID,
    before_state    JSONB,
    after_state     JSONB,
    ip_address      INET,
    created_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_audit_actor ON audit_logs(actor_user_id);
CREATE INDEX idx_audit_entity ON audit_logs(entity_type, entity_id);""")
    


def downgrade() -> None:
    # Reverse order — children PEHLE drop, warna FK violation aayega na bidu

    op.execute("DROP TABLE IF EXISTS audit_logs;")
    op.execute("DROP TABLE IF EXISTS response_history;")
    op.execute("DROP TABLE IF EXISTS rescue_timeline;")
    op.execute("DROP TABLE IF EXISTS notifications;")
    op.execute("DROP TABLE IF EXISTS emergency_requests;")
    op.execute("DROP TABLE IF EXISTS images;")
    op.execute("DROP TABLE IF EXISTS reports;")
    op.execute("DROP TABLE IF EXISTS locations;")
    op.execute("DROP TABLE IF EXISTS animals;")
    op.execute("DROP TABLE IF EXISTS shelters;")
    op.execute("DROP TABLE IF EXISTS volunteers;")
    op.execute("DROP TABLE IF EXISTS veterinarians;")
    op.execute("DROP TABLE IF EXISTS organizations;")
    op.execute("DROP TABLE IF EXISTS users;")
    
