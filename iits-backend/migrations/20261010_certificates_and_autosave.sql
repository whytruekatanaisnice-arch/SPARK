DO $$
BEGIN
    CREATE TYPE absence_certificate_status AS ENUM ('pending', 'approved', 'rejected');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END
$$;

CREATE TABLE IF NOT EXISTS absence_certificates (
    id uuid PRIMARY KEY,
    student_id uuid NOT NULL REFERENCES users(id),
    uploaded_by uuid NOT NULL REFERENCES users(id),
    absence_date date NOT NULL,
    description varchar(1000),
    file_path varchar(500) NOT NULL,
    status absence_certificate_status NOT NULL DEFAULT 'pending',
    review_note text,
    reviewed_by uuid REFERENCES users(id),
    reviewed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_absence_certificates_student_id
    ON absence_certificates (student_id);
CREATE INDEX IF NOT EXISTS ix_absence_certificates_absence_date
    ON absence_certificates (absence_date);
CREATE INDEX IF NOT EXISTS ix_absence_certificates_status
    ON absence_certificates (status);

CREATE TABLE IF NOT EXISTS autosave_drafts (
    id uuid PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES users(id),
    page_key varchar(512) NOT NULL,
    data jsonb NOT NULL DEFAULT '{}'::jsonb,
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_autosave_user_page UNIQUE (user_id, page_key)
);

CREATE INDEX IF NOT EXISTS ix_autosave_drafts_user_id
    ON autosave_drafts (user_id);
