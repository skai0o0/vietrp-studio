-- Dev/test databases for VietRP Studio on this machine. Run once as the postgres superuser,
-- passing the password you put in backend/.env (DATABASE_URL):
--   "C:/Program Files/PostgreSQL/17/bin/psql.exe" -h 127.0.0.1 -U postgres -v db_password=<password> -f scripts/dev/create-dev-db.sql
CREATE ROLE vietrp_studio LOGIN PASSWORD :'db_password';
CREATE DATABASE vietrp_studio OWNER vietrp_studio ENCODING 'UTF8' TEMPLATE template0;
CREATE DATABASE vietrp_studio_test OWNER vietrp_studio ENCODING 'UTF8' TEMPLATE template0;
\connect vietrp_studio
CREATE EXTENSION IF NOT EXISTS pgcrypto;
\connect vietrp_studio_test
CREATE EXTENSION IF NOT EXISTS pgcrypto;
