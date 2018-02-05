DROP TABLE IF EXISTS users;
CREATE TABLE users (
  username VARCHAR(40) NOT NULL DEFAULT '',
  password VARCHAR(40) NOT NULL DEFAULT '',
  display_name VARCHAR(128) DEFAULT NULL,
  email VARCHAR(255) DEFAULT NULL,
  is_enabled TINYINT DEFAULT 0,
  is_qa TINYINT DEFAULT 0,
  is_analyst TINYINT DEFAULT 0,
  group_id VARCHAR(40) DEFAULT NULL,
  is_locked TINYINT DEFAULT 0,
  UNIQUE KEY id (username)
) CHARSET=utf8;
INSERT INTO users (username, password, display_name, email, is_enabled, is_qa, is_analyst, is_locked, group_id)
    VALUES ('admin', '5459dbe5e9aa80e077bfa40f3fb2ca8368ed09b4', 'Admin User', 'sign-test@fwupd.org', 1, 1, 1, 0, 'admin');

DROP TABLE IF EXISTS vendors;
CREATE TABLE vendors (
  group_id VARCHAR(40) NOT NULL DEFAULT '',
  display_name VARCHAR(128) NOT NULL DEFAULT '',
  plugins VARCHAR(128) DEFAULT NULL,
  description VARCHAR(255) NOT NULL DEFAULT '',
  visible TINYINT DEFAULT 0,
  is_fwupd_supported VARCHAR(16) NOT NULL DEFAULT 'no',
  is_account_holder VARCHAR(16) NOT NULL DEFAULT 'no',
  is_uploading VARCHAR(16) NOT NULL DEFAULT 'no',
  comments VARCHAR(255) NOT NULL DEFAULT '',
  UNIQUE KEY id (group_id)
) CHARSET=utf8;

-- the cab file
DROP TABLE IF EXISTS firmware;
CREATE TABLE firmware (

  -- information about the upload
  group_id VARCHAR(40) DEFAULT NULL,            -- QA group of uploader
  addr VARCHAR(40) DEFAULT NULL,                -- IP address of uploader
  timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, -- upload date/time
  filename VARCHAR(255) DEFAULT NULL,           -- filename of the original .cab file

  -- information about the download
  download_cnt INT DEFAULT 0,                   -- generated from the client database

  -- parsed from the uploaded data
  firmware_id VARCHAR(40) DEFAULT NULL,         -- SHA1 of the original .cab file
  version_display VARCHAR(255) DEFAULT NULL,    -- from the firmware.inf file

  -- modified as the firmware is tested
  target VARCHAR(255) DEFAULT NULL,             -- pivate, embargo, testing, etc.

  UNIQUE KEY id (firmware_id)
) CHARSET=utf8;

-- the metainfo file
DROP TABLE IF EXISTS firmware_md;
CREATE TABLE firmware_md (

  metainfo_id VARCHAR(40) DEFAULT NULL,         -- SHA1 of the metainfo.xml file
  firmware_id VARCHAR(40) DEFAULT NULL,         -- which cab file owns this?
  checksum_contents VARCHAR(40) DEFAULT NULL,   -- SHA1 of the firmware.bin
  checksum_container VARCHAR(40) DEFAULT NULL,  -- SHA1 of the signed .cab file

  -- information parsed from the metainfo file XML
  id TEXT DEFAULT NULL,                         -- e.g. com.hughski.ColorHug.firmware
  name TEXT DEFAULT NULL,
  summary TEXT DEFAULT NULL,
  guid TEXT DEFAULT NULL,
  description TEXT DEFAULT NULL,
  release_description TEXT DEFAULT NULL,
  url_homepage TEXT DEFAULT NULL,
  metadata_license TEXT DEFAULT NULL,
  project_license TEXT DEFAULT NULL,
  developer_name TEXT DEFAULT NULL,
  filename_contents TEXT DEFAULT NULL,          -- filename of the firmware.bin
  release_timestamp INTEGER DEFAULT 0,
  version VARCHAR(255) DEFAULT NULL,
  release_installed_size INTEGER DEFAULT 0,
  release_download_size INTEGER DEFAULT 0,
  release_urgency VARCHAR(16) DEFAULT NULL,
  screenshot_url TEXT DEFAULT NULL,
  screenshot_caption TEXT DEFAULT NULL,
  requirements TEXT DEFAULT NULL,               -- requirements, e.g. "id/fwupd/ge/0.8.2"
  UNIQUE KEY id (firmware_id,metainfo_id)
) CHARSET=utf8;

DROP TABLE IF EXISTS event_log;
CREATE TABLE event_log (
  id INT NOT NULL AUTO_INCREMENT,
  timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  username VARCHAR(40) NOT NULL DEFAULT '',
  group_id VARCHAR(40) DEFAULT NULL,
  addr VARCHAR(40) DEFAULT NULL,
  message TEXT DEFAULT NULL,
  is_important TINYINT DEFAULT 0,
  request TEXT DEFAULT NULL,
  UNIQUE KEY id (id)
) CHARSET=utf8;

DROP TABLE IF EXISTS clients;
CREATE TABLE clients (
  id INT NOT NULL AUTO_INCREMENT,
  timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  addr VARCHAR(40) DEFAULT NULL,
  filename VARCHAR(256) DEFAULT NULL,
  user_agent VARCHAR(256) DEFAULT NULL,
  UNIQUE KEY id (id)
) CHARSET=utf8;
CREATE INDEX filename_idx ON clients (filename(40));

DROP TABLE IF EXISTS groups;
CREATE TABLE groups (
  group_id VARCHAR(40) DEFAULT NULL,
  vendor_ids VARCHAR(40) NOT NULL DEFAULT '',
  UNIQUE KEY id (group_id)
) CHARSET=utf8;

DROP TABLE IF EXISTS analytics;
CREATE TABLE analytics (
  datestr INT DEFAULT 0,
  kind TINYINT DEFAULT 0,
  cnt INT DEFAULT 1,
  UNIQUE (datestr,kind)
) CHARSET=utf8;

DROP TABLE IF EXISTS reports;
CREATE TABLE reports (
  id INT NOT NULL AUTO_INCREMENT,
  timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  state TINYINT DEFAULT 0,
  json TEXT DEFAULT NULL,
  machine_id VARCHAR(64) DEFAULT NULL,
  firmware_id VARCHAR(40) DEFAULT NULL,
  checksum VARCHAR(64) DEFAULT NULL,
  UNIQUE KEY id (id)
) CHARSET=utf8;

DROP TABLE IF EXISTS settings;
CREATE TABLE settings (
  id INT NOT NULL AUTO_INCREMENT,
  config_key TEXT DEFAULT NULL,
  config_value TEXT DEFAULT NULL,
  UNIQUE KEY id (id)
) CHARSET=utf8;
