CREATE TABLE IF NOT EXISTS segak_assessments (
    id uuid PRIMARY KEY,
    student_id uuid NOT NULL REFERENCES users(id),
    assessed_by uuid NOT NULL REFERENCES users(id),
    assessment_date date NOT NULL,
    weight_kg numeric(5, 2),
    height_cm numeric(5, 2),
    bmi numeric(5, 2),
    step_test_recovery_bpm integer,
    push_up_type varchar(20),
    push_up_reps integer,
    curl_up_reps integer,
    sit_and_reach_cm numeric(5, 2),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_segak_student_assessment_date UNIQUE (student_id, assessment_date),
    CONSTRAINT ck_segak_weight_range CHECK (weight_kg IS NULL OR (weight_kg > 0 AND weight_kg <= 300)),
    CONSTRAINT ck_segak_height_range CHECK (height_cm IS NULL OR (height_cm > 0 AND height_cm <= 250)),
    CONSTRAINT ck_segak_bmi_positive CHECK (bmi IS NULL OR bmi > 0),
    CONSTRAINT ck_segak_step_test_range CHECK (
        step_test_recovery_bpm IS NULL OR step_test_recovery_bpm BETWEEN 20 AND 250
    ),
    CONSTRAINT ck_segak_push_up_type CHECK (
        push_up_type IS NULL OR push_up_type IN ('standard', 'modified')
    ),
    CONSTRAINT ck_segak_push_up_pair CHECK (
        (push_up_type IS NULL AND push_up_reps IS NULL)
        OR (push_up_type IS NOT NULL AND push_up_reps IS NOT NULL)
    ),
    CONSTRAINT ck_segak_push_up_reps_range CHECK (
        push_up_reps IS NULL OR push_up_reps BETWEEN 0 AND 300
    ),
    CONSTRAINT ck_segak_curl_up_reps_range CHECK (
        curl_up_reps IS NULL OR curl_up_reps BETWEEN 0 AND 300
    ),
    CONSTRAINT ck_segak_sit_and_reach_range CHECK (
        sit_and_reach_cm IS NULL OR sit_and_reach_cm BETWEEN -50 AND 100
    )
);

CREATE INDEX IF NOT EXISTS ix_segak_assessments_student_id
    ON segak_assessments (student_id);
CREATE INDEX IF NOT EXISTS ix_segak_assessments_assessment_date
    ON segak_assessments (assessment_date);
