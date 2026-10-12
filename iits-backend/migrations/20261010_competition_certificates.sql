DO $$
BEGIN
    CREATE TYPE competition_certificate_status AS ENUM ('draft', 'pending', 'approved', 'rejected');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END
$$;

CREATE TABLE IF NOT EXISTS competition_certificates (
    id uuid PRIMARY KEY,
    student_id uuid NOT NULL REFERENCES users(id),
    submitted_by uuid NOT NULL REFERENCES users(id),
    status competition_certificate_status NOT NULL DEFAULT 'draft',
    file_path varchar(500) NOT NULL,
    file_sha256 varchar(64) NOT NULL,
    ocr_text text NOT NULL,
    event_name varchar(255),
    event_key varchar(255),
    organizer varchar(255),
    awardee_name varchar(255),
    event_date date,
    competition_level varchar(30),
    participation_type varchar(1),
    placement varchar(20),
    engagement_score integer,
    achievement_score integer,
    score integer,
    review_note text,
    reviewed_by uuid REFERENCES users(id),
    reviewed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_competition_certificate_submitted_fields CHECK (
        status NOT IN ('pending', 'approved') OR (
            event_name IS NOT NULL AND event_key IS NOT NULL AND event_date IS NOT NULL
            AND organizer IS NOT NULL AND awardee_name IS NOT NULL AND competition_level IS NOT NULL
            AND participation_type IS NOT NULL AND engagement_score IS NOT NULL
            AND achievement_score IS NOT NULL AND score IS NOT NULL
        )
    )
);

CREATE INDEX IF NOT EXISTS ix_competition_certificates_student_id
    ON competition_certificates (student_id);
CREATE INDEX IF NOT EXISTS ix_competition_certificates_status
    ON competition_certificates (status);
CREATE UNIQUE INDEX IF NOT EXISTS uq_competition_certificate_event
    ON competition_certificates (student_id, event_date, event_key)
    WHERE status IN ('pending', 'approved');
CREATE UNIQUE INDEX IF NOT EXISTS uq_competition_certificate_file
    ON competition_certificates (student_id, file_sha256)
    WHERE status IN ('pending', 'approved');

INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
    'achievement-certificates',
    'achievement-certificates',
    false,
    10485760,
    ARRAY['application/pdf', 'image/jpeg', 'image/png']
)
ON CONFLICT (id) DO UPDATE
SET public = false,
    file_size_limit = EXCLUDED.file_size_limit,
    allowed_mime_types = EXCLUDED.allowed_mime_types;
