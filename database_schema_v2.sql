-- ============================================================
-- ARISE - Skema Database PostgreSQL v2
-- ============================================================
-- Aman untuk pengembangan: mendukung user_id string dari Unity melalui
-- users.external_user_id, menyimpan sesi, profil, skenario aktif,
-- used_scenario_ids, dan riwayat jawaban per ronde.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ------------------------------------------------------------
-- 1. Pengguna
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    external_user_id    VARCHAR(100) UNIQUE NOT NULL,
    full_name           VARCHAR(150) NOT NULL DEFAULT 'Pengguna ARISE',
    role                VARCHAR(20) NOT NULL DEFAULT 'siswa' CHECK (role IN ('siswa', 'pendamping', 'admin')),
    institution         VARCHAR(200),
    guardian_id         UUID REFERENCES users(id),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_users_external_user_id ON users(external_user_id);

-- ------------------------------------------------------------
-- 2. Hasil Asesmen & Profil Kognitif
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cognitive_profiles (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    profile_category    VARCHAR(40) NOT NULL CHECK (profile_category IN ('visual_cepat', 'tekstual_sedang', 'butuh_pendampingan')),
    avg_response_time   NUMERIC(6,2) NOT NULL,
    accuracy_rate       NUMERIC(4,3) NOT NULL,
    variability         NUMERIC(6,2) NOT NULL,
    reduced_motion      BOOLEAN NOT NULL DEFAULT false,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cognitive_profiles_user ON cognitive_profiles(user_id);

-- ------------------------------------------------------------
-- 3. Bank Skenario & Opsi Jawaban
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS scenarios (
    id          INTEGER PRIMARY KEY,
    level       SMALLINT NOT NULL CHECK (level BETWEEN 1 AND 3),
    category    VARCHAR(80) NOT NULL,
    sender      VARCHAR(120) NOT NULL,
    message     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scenario_options (
    id              SERIAL PRIMARY KEY,
    scenario_id     INTEGER NOT NULL REFERENCES scenarios(id) ON DELETE CASCADE,
    option_code     CHAR(1) NOT NULL CHECK (option_code IN ('a', 'b')),
    label           VARCHAR(180) NOT NULL,
    is_correct      BOOLEAN NOT NULL,
    ar_mode         VARCHAR(30) NOT NULL CHECK (ar_mode IN ('leak', 'safe', 'footprint-high', 'footprint-low', 'shield-cracked', 'shield-intact')),
    feedback        TEXT NOT NULL,
    UNIQUE (scenario_id, option_code)
);

CREATE INDEX IF NOT EXISTS idx_scenario_options_scenario ON scenario_options(scenario_id);

-- ------------------------------------------------------------
-- 4. Sesi Latihan
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sessions (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    cognitive_profile_id    UUID REFERENCES cognitive_profiles(id),
    current_level           SMALLINT NOT NULL DEFAULT 1 CHECK (current_level BETWEEN 1 AND 3),
    used_scenario_ids       INTEGER[] NOT NULL DEFAULT '{}',
    current_scenario_id     INTEGER REFERENCES scenarios(id),
    started_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at                TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);

-- ------------------------------------------------------------
-- 5. Riwayat Respons per Ronde
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS session_responses (
    id                      BIGSERIAL PRIMARY KEY,
    session_id              UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    round_number            SMALLINT NOT NULL,
    scenario_id             INTEGER NOT NULL REFERENCES scenarios(id),
    option_id               INTEGER NOT NULL REFERENCES scenario_options(id),
    is_correct              BOOLEAN NOT NULL,
    level_before            SMALLINT NOT NULL,
    level_after             SMALLINT NOT NULL,
    response_time_seconds   NUMERIC(6,2) NOT NULL,
    ar_mode_shown           VARCHAR(30) NOT NULL,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (session_id, round_number)
);

CREATE INDEX IF NOT EXISTS idx_session_responses_session ON session_responses(session_id);

-- ------------------------------------------------------------
-- 6. View Ringkasan Dashboard
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW v_session_summary AS
SELECT
    s.id                                      AS session_id,
    s.user_id,
    u.external_user_id,
    u.full_name,
    cp.profile_category,
    s.current_level,
    COUNT(sr.id)                             AS rounds_completed,
    COUNT(sr.id) FILTER (WHERE sr.is_correct) AS correct_total,
    ROUND(AVG(sr.response_time_seconds), 2)  AS avg_response_time,
    s.started_at,
    s.ended_at
FROM sessions s
JOIN users u ON u.id = s.user_id
LEFT JOIN cognitive_profiles cp ON cp.id = s.cognitive_profile_id
LEFT JOIN session_responses sr ON sr.session_id = s.id
GROUP BY s.id, u.id, u.external_user_id, u.full_name, cp.profile_category;

-- ------------------------------------------------------------
-- 7. Seed Bank Skenario
-- ------------------------------------------------------------
INSERT INTO scenarios (id, level, category, sender, message) VALUES
 (1, 1, 'Tautan Mencurigakan', 'Admin Bank Sejahtera',
  'PERINGATAN: Akun Anda akan diblokir hari ini! Klik tautan ini sekarang untuk verifikasi: bit.ly/verifikasi-akun'),
 (2, 1, 'Permintaan Data Pribadi', 'No. Tidak Dikenal',
  'Selamat! Nomormu menang hadiah HP baru. Kirim foto KTP dan nomor rekening untuk klaim hadiah sekarang.'),
 (3, 1, 'Kata Sandi', 'Sistem Belajar Daring',
  'Buat kata sandi baru untuk akun belajar daringmu.'),
 (4, 2, 'Permintaan Data Pribadi', 'Teman Baru di Game',
  'Halo! Aku temanmu di game. Boleh kirim alamat rumah dan nomor HP-mu? Aku mau kirim hadiah.'),
 (5, 2, 'Kode Rahasia (OTP)', 'Teman Sekelas',
  'Eh, kode OTP yang baru masuk ke HP-mu itu salah kirim, punyaku. Tolong kirim kodenya ke aku ya.'),
 (6, 2, 'Izin Aplikasi', 'Aplikasi Game Baru',
  'Aplikasi ini minta izin membaca semua foto dan kontak di HP-mu agar "lebih seru". Izinkan?'),
 (7, 3, 'Penipuan Berkedok Lowongan', 'Info Lowongan Kerja',
  'Lowongan kerja paruh waktu, gaji besar! Transfer Rp50.000 ke No. Rekening 12345 untuk biaya pendaftaran.'),
 (8, 3, 'WiFi Publik', 'Notifikasi WiFi',
  'WiFi gratis "Free_Public_WiFi" tersedia. Buka aplikasi m-banking sekarang menggunakan WiFi ini?')
ON CONFLICT (id) DO UPDATE SET
    level = EXCLUDED.level,
    category = EXCLUDED.category,
    sender = EXCLUDED.sender,
    message = EXCLUDED.message;

INSERT INTO scenario_options (scenario_id, option_code, label, is_correct, ar_mode, feedback) VALUES
 (1, 'a', 'Klik tautannya', false, 'leak',
  'Hati-hati! Tautan seperti ini sering dipakai untuk mencuri data pribadimu.'),
 (1, 'b', 'Laporkan & abaikan', true, 'safe',
  'Tepat! Pesan yang membuatmu panik dan minta klik cepat biasanya berbahaya.'),
 (2, 'a', 'Kirim KTP & rekening', false, 'footprint-high',
  'KTP dan nomor rekening adalah data penting. Jangan dikirim ke nomor tidak dikenal.'),
 (2, 'b', 'Tidak membalas', true, 'footprint-low',
  'Tepat! Hadiah yang meminta data pribadi biasanya adalah penipuan.'),
 (3, 'a', 'Gunakan "123456"', false, 'shield-cracked',
  'Kata sandi seperti ini sangat mudah ditebak orang lain.'),
 (3, 'b', 'Gunakan "Bunga#Ceria25"', true, 'shield-intact',
  'Bagus! Campuran huruf, angka, dan simbol lebih sulit ditebak.'),
 (4, 'a', 'Kirim alamat & no. HP', false, 'footprint-high',
  'Orang yang baru dikenal di internet sebaiknya tidak diberi alamat rumahmu.'),
 (4, 'b', 'Tanya orang dewasa dulu', true, 'footprint-low',
  'Tepat! Bicarakan dulu dengan orang dewasa yang kamu percaya.'),
 (5, 'a', 'Kirim kode OTP', false, 'leak',
  'Kode OTP adalah kunci rahasia akunmu. Jangan dibagikan, walau diminta teman.'),
 (5, 'b', 'Tidak mengirim kode', true, 'safe',
  'Tepat! Kode OTP hanya untukmu sendiri, tidak untuk siapa pun.'),
 (6, 'a', 'Izinkan semua', false, 'footprint-high',
  'Izin yang terlalu luas membuat data pribadimu tersebar ke aplikasi tersebut.'),
 (6, 'b', 'Tolak yang tidak perlu', true, 'footprint-low',
  'Tepat! Berikan izin secukupnya saja.'),
 (7, 'a', 'Transfer uang', false, 'leak',
  'Lowongan asli tidak pernah meminta transfer uang di awal.'),
 (7, 'b', 'Cek kebenarannya dulu', true, 'safe',
  'Tepat! Selalu cek kebenaran info sebelum mengirim uang.'),
 (8, 'a', 'Buka m-Banking', false, 'shield-cracked',
  'WiFi publik kurang aman untuk membuka akun penting seperti m-banking.'),
 (8, 'b', 'Tunggu jaringan aman', true, 'shield-intact',
  'Tepat! Gunakan jaringan yang kamu percaya untuk akun penting.')
ON CONFLICT (scenario_id, option_code) DO UPDATE SET
    label = EXCLUDED.label,
    is_correct = EXCLUDED.is_correct,
    ar_mode = EXCLUDED.ar_mode,
    feedback = EXCLUDED.feedback;
