-- Create uspto_trademark_emails: one row per email per case.
-- email_sent = single email for this row; email_r_to_sent = full list (email1,email2,email3).
-- Composite primary key: (serial_number, status_code, email_sent).

CREATE TABLE dbo.uspto_trademark_emails (
    serial_number          VARCHAR(50)   NOT NULL,
    status_code            VARCHAR(10)   NOT NULL,
    email_sent             VARCHAR(255)  NOT NULL,
    email_r_to_sent        VARCHAR(2000) NOT NULL,
    refresh_date           DATE          NOT NULL,

    filing_date            DATE          NULL,
    status_description     VARCHAR(500)  NULL,
    attorney_name          VARCHAR(500)  NULL,
    attorney_email         VARCHAR(255)  NULL,
    correspondent_name     VARCHAR(500)  NULL,
    correspondent_email    VARCHAR(500)  NULL,
    prosecution_date       VARCHAR(100)  NULL,
    prosecution_description VARCHAR(1000) NULL,
    url                    VARCHAR(1000) NULL,
    correspondent_address  VARCHAR(1000) NULL,
    owner_name             VARCHAR(500)  NULL,
    owner_address          VARCHAR(1000) NULL,
    most_recent_status_date DATE         NULL,

    created_at             DATETIME2     NOT NULL DEFAULT GETDATE(),

    PRIMARY KEY (serial_number, status_code, email_sent)
);
GO
