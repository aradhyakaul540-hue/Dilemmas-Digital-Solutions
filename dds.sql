CREATE DATABASE dds_leads;

USE dds_leads;

CREATE TABLE contacts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100),
    company VARCHAR(100),
    phone VARCHAR(20),
    email VARCHAR(100),
    address TEXT,
    service VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
USE dds_leads;

CREATE TABLE admins (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50),
    password VARCHAR(255)
);

USE admins;

INSERT INTO admins (username, password)
VALUES ('DDS-CEO','Tanishq@dds1');

INSERT INTO admins (username, password)
VALUES ('DDS-Kaul','Kaul@dds1');

ALTER TABLE contacts
ADD COLUMN notes TEXT;

SELECT username,password from admins;

ALTER TABLE admins ADD COLUMN role VARCHAR(20) DEFAULT 'manager';


CREATE TABLE lead_notes (
id INT AUTO_INCREMENT PRIMARY KEY,
lead_id INT,
note TEXT,
created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

UPDATE admins
SET password = 'PASTE_HASH_FOR_CEO'
WHERE username = 'DDS-CEO';

UPDATE admins
SET password = 'PASTE_HASH_FOR_KAUL'
WHERE username = 'DDS-Kaul';
SET SQL_SAFE_UPDATES = 1;

SELECT username,password from admins;
DELETE FROM admins;

ALTER TABLE admins
ADD COLUMN role VARCHAR(20) DEFAULT 'Sales';

ALTER TABLE admins ADD COLUMN role VARCHAR(20) DEFAULT 'Sales';

UPDATE admins SET role='CEO' WHERE username='DDS-CEO';
UPDATE admins SET role='Manager' WHERE username='DDS-Kaul';

