-- Drop existing table uspto_trademark_emails (if exists).
-- Run this before creating the new table. All data in the table will be lost.

IF OBJECT_ID('dbo.uspto_trademark_emails', 'U') IS NOT NULL
    DROP TABLE dbo.uspto_trademark_emails;
GO
