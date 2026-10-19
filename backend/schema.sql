-- 기동 시 그대로 실행된다. 모든 문장은 여러 번 실행해도 안전해야 한다.

CREATE TABLE IF NOT EXISTS recalls (
    id                bigserial PRIMARY KEY,
    source            text        NOT NULL,
    source_id         text        NOT NULL,
    category          text        NOT NULL,
    product_name      text,
    company_name      text,
    reason            text,
    grade             smallint    CHECK (grade BETWEEN 1 AND 3),
    manufactured_text text,
    expiry_text       text,
    package_unit      text,
    recall_method     text,
    address           text,
    company_phone     text,
    barcode           text,
    image_urls        jsonb       NOT NULL DEFAULT '[]'::jsonb,
    source_url        text,
    registered_at     timestamptz NOT NULL,
    first_seen_at     timestamptz NOT NULL DEFAULT now(),
    last_seen_at      timestamptz NOT NULL DEFAULT now(),
    raw               jsonb       NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (source, source_id)
);

-- 처음 만든 뒤 추가된 열. 이미 있는 테이블에도 붙도록 ALTER로 둔다.
ALTER TABLE recalls ADD COLUMN IF NOT EXISTS source_label       text;
ALTER TABLE recalls ADD COLUMN IF NOT EXISTS model_text         text;
ALTER TABLE recalls ADD COLUMN IF NOT EXISTS consumer_tips      text;
ALTER TABLE recalls ADD COLUMN IF NOT EXISTS recall_period_text text;

CREATE TABLE IF NOT EXISTS source_state (
    source          text PRIMARY KEY,
    last_success_at timestamptz,
    last_error_at   timestamptz,
    last_error      text,
    last_row_count  integer
);
