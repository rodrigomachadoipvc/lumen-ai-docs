-- Runs once, when the postgres volume is first created.
-- Alembic migrations also enable the extension, so this only makes a fresh local DB usable right away.
CREATE EXTENSION IF NOT EXISTS vector;

-- Separate database for the optional Langfuse profile, so its tables never mix with Lumen's.
CREATE DATABASE langfuse;
