"""
ARISE - AI Engine Lightweight Deploy Variant
============================================

Versi ini disiapkan untuk deployment serverless/free-tier yang tidak cocok
dengan dependency besar seperti scikit-learn.

Endpoint tetap sama.
Logika tetap:
- profiling kognitif awal berbasis avg_time, accuracy, variability
- adaptasi level berdasarkan benar/salah
- pemilihan skenario sesuai level dan menghindari pengulangan

Catatan presentasi:
Versi lokal utama tetap dapat memakai DecisionTreeClassifier.
Versi cloud ini adalah lightweight inference fallback agar demo online bisa stabil.
"""

import random

SCENARIOS = [{'id': 1, 'level': 1, 'category': 'Tautan Mencurigakan', 'sender': 'Admin Bank Sejahtera', 'message': 'PERINGATAN: Akun Anda akan diblokir hari ini! Klik tautan ini sekarang untuk verifikasi: bit.ly/verifikasi-akun', 'options': [{'id': 'a', 'label': 'Klik tautannya', 'correct': False, 'arMode': 'leak', 'feedback': 'Hati-hati! Tautan seperti ini sering dipakai untuk mencuri data pribadimu.'}, {'id': 'b', 'label': 'Laporkan & abaikan', 'correct': True, 'arMode': 'safe', 'feedback': 'Tepat! Pesan yang membuatmu panik dan minta klik cepat biasanya berbahaya.'}]}, {'id': 2, 'level': 1, 'category': 'Permintaan Data Pribadi', 'sender': 'No. Tidak Dikenal', 'message': 'Selamat! Nomormu menang hadiah HP baru. Kirim foto KTP dan nomor rekening untuk klaim hadiah sekarang.', 'options': [{'id': 'a', 'label': 'Kirim KTP & rekening', 'correct': False, 'arMode': 'footprint-high', 'feedback': 'KTP dan nomor rekening adalah data penting. Jangan dikirim ke nomor tidak dikenal.'}, {'id': 'b', 'label': 'Tidak membalas', 'correct': True, 'arMode': 'footprint-low', 'feedback': 'Tepat! Hadiah yang meminta data pribadi biasanya adalah penipuan.'}]}, {'id': 3, 'level': 1, 'category': 'Kata Sandi', 'sender': 'Sistem Belajar Daring', 'message': 'Buat kata sandi baru untuk akun belajar daringmu.', 'options': [{'id': 'a', 'label': 'Gunakan "123456"', 'correct': False, 'arMode': 'shield-cracked', 'feedback': 'Kata sandi seperti ini sangat mudah ditebak orang lain.'}, {'id': 'b', 'label': 'Gunakan "Bunga#Ceria25"', 'correct': True, 'arMode': 'shield-intact', 'feedback': 'Bagus! Campuran huruf, angka, dan simbol lebih sulit ditebak.'}]}, {'id': 4, 'level': 2, 'category': 'Permintaan Data Pribadi', 'sender': 'Teman Baru di Game', 'message': 'Halo! Aku temanmu di game. Boleh kirim alamat rumah dan nomor HP-mu? Aku mau kirim hadiah.', 'options': [{'id': 'a', 'label': 'Kirim alamat & no. HP', 'correct': False, 'arMode': 'footprint-high', 'feedback': 'Orang yang baru dikenal di internet sebaiknya tidak diberi alamat rumahmu.'}, {'id': 'b', 'label': 'Tanya orang dewasa dulu', 'correct': True, 'arMode': 'footprint-low', 'feedback': 'Tepat! Bicarakan dulu dengan orang dewasa yang kamu percaya.'}]}, {'id': 5, 'level': 2, 'category': 'Kode Rahasia (OTP)', 'sender': 'Teman Sekelas', 'message': 'Eh, kode OTP yang baru masuk ke HP-mu itu salah kirim, punyaku. Tolong kirim kodenya ke aku ya.', 'options': [{'id': 'a', 'label': 'Kirim kode OTP', 'correct': False, 'arMode': 'leak', 'feedback': 'Kode OTP adalah kunci rahasia akunmu. Jangan dibagikan, walau diminta teman.'}, {'id': 'b', 'label': 'Tidak mengirim kode', 'correct': True, 'arMode': 'safe', 'feedback': 'Tepat! Kode OTP hanya untukmu sendiri, tidak untuk siapa pun.'}]}, {'id': 6, 'level': 2, 'category': 'Izin Aplikasi', 'sender': 'Aplikasi Game Baru', 'message': 'Aplikasi ini minta izin membaca semua foto dan kontak di HP-mu agar "lebih seru". Izinkan?', 'options': [{'id': 'a', 'label': 'Izinkan semua', 'correct': False, 'arMode': 'footprint-high', 'feedback': 'Izin yang terlalu luas membuat data pribadimu tersebar ke aplikasi tersebut.'}, {'id': 'b', 'label': 'Tolak yang tidak perlu', 'correct': True, 'arMode': 'footprint-low', 'feedback': 'Tepat! Berikan izin secukupnya saja.'}]}, {'id': 7, 'level': 3, 'category': 'Penipuan Berkedok Lowongan', 'sender': 'Info Lowongan Kerja', 'message': 'Lowongan kerja paruh waktu, gaji besar! Transfer Rp50.000 ke No. Rekening 12345 untuk biaya pendaftaran.', 'options': [{'id': 'a', 'label': 'Transfer uang', 'correct': False, 'arMode': 'leak', 'feedback': 'Lowongan asli tidak pernah meminta transfer uang di awal.'}, {'id': 'b', 'label': 'Cek kebenarannya dulu', 'correct': True, 'arMode': 'safe', 'feedback': 'Tepat! Selalu cek kebenaran info sebelum mengirim uang.'}]}, {'id': 8, 'level': 3, 'category': 'WiFi Publik', 'sender': 'Notifikasi WiFi', 'message': 'WiFi gratis "Free_Public_WiFi" tersedia. Buka aplikasi m-banking sekarang menggunakan WiFi ini?', 'options': [{'id': 'a', 'label': 'Buka m-Banking', 'correct': False, 'arMode': 'shield-cracked', 'feedback': 'WiFi publik kurang aman untuk membuka akun penting seperti m-banking.'}, {'id': 'b', 'label': 'Tunggu jaringan aman', 'correct': True, 'arMode': 'shield-intact', 'feedback': 'Tepat! Gunakan jaringan yang kamu percaya untuk akun penting.'}]}]

PROFILE_DESCRIPTIONS = {'visual_cepat': {'label': 'Pembelajar Visual, Respons Cepat', 'description': 'Pengguna merespons dengan cepat dan akurat. Skenario dapat disajikan dengan kompleksitas visual standar.', 'reduced_motion': False}, 'tekstual_sedang': {'label': 'Pembelajar Bertahap, Respons Sedang', 'description': 'Pengguna membutuhkan waktu sedikit lebih lama untuk memahami instruksi. Disarankan repetisi sedang dan narasi audio aktif.', 'reduced_motion': False}, 'butuh_pendampingan': {'label': 'Membutuhkan Pendampingan Lebih', 'description': 'Pengguna membutuhkan waktu lebih lama dan tingkat kesalahan awal lebih tinggi. Disarankan mode animasi sederhana, repetisi tinggi, dan keterlibatan pendamping aktif.', 'reduced_motion': True}}


class CognitiveProfiler:
    """Profiling ringan berbasis aturan untuk deployment cloud/serverless."""

    def predict(self, avg_response_time: float, accuracy_rate: float, variability: float):
        if accuracy_rate >= 0.75 and avg_response_time <= 4.0 and variability <= 1.5:
            profile = "visual_cepat"
        elif accuracy_rate >= 0.55 and avg_response_time <= 7.5:
            profile = "tekstual_sedang"
        else:
            profile = "butuh_pendampingan"

        proba = {
            "visual_cepat": 0.0,
            "tekstual_sedang": 0.0,
            "butuh_pendampingan": 0.0,
        }
        proba[profile] = 1.0
        return profile, proba


def next_level(current_level: int, correct: bool) -> int:
    if correct:
        return min(current_level + 1, 3)
    return max(current_level - 1, 1)


def pick_scenario(level: int, used_ids: list):
    pool = [s for s in SCENARIOS if s["level"] == level and s["id"] not in used_ids]
    if not pool:
        pool = [s for s in SCENARIOS if s["level"] == level]
    return random.choice(pool)
