# ARISE — Deploy FastAPI ke Vercel + Neon

## Kenapa Vercel?
Render dan Hugging Face Docker bisa meminta kartu/plan berbayar.
Vercel bisa dicoba sebagai jalur serverless tanpa Docker.

## Catatan Penting
Paket ini memakai `arise_ai_engine.py` versi lightweight:
- tidak memakai `scikit-learn`
- tidak memakai `numpy`
- endpoint tetap sama
- profiling tetap adaptif berbasis aturan
- skenario dan AR mode tetap sama

Tujuannya agar cocok dengan free/serverless deployment.

## Isi yang Harus Diupload ke GitHub
Upload semua isi folder ini ke repo baru, misalnya:

```text
arise-vercel-api
```

Isi:
- api/index.py
- backend_api_db_fallback.py
- db_utils.py
- arise_ai_engine.py
- database_schema_v2.sql
- requirements.txt
- vercel.json
- init_db.py
- test_deployed_api.py
- .env.example
- README_VERCEL_DEPLOY_ARISE.md

Jangan upload `.env` berisi password.

## Environment Variables di Vercel
Di Vercel Project Settings → Environment Variables:

```text
DATABASE_URL = connection string Neon
ARISE_USE_DB = 1
```

Connection string Neon harus seperti:

```text
postgresql://USER:PASSWORD@HOST.neon.tech/arise_db?sslmode=require
```

## Inisialisasi Database Neon
Di PowerShell folder ini:

```powershell
$env:DATABASE_URL="PASTE_CONNECTION_STRING_NEON"
python init_db.py
```

## Test Setelah Deploy
URL Vercel akan seperti:

```text
https://arise-vercel-api.vercel.app
```

Cek:

```text
https://arise-vercel-api.vercel.app/health
https://arise-vercel-api.vercel.app/docs
```

Test otomatis:

```powershell
python test_deployed_api.py https://arise-vercel-api.vercel.app
```

## Unity
Jika test lolos, ubah `ApiManager.baseUrl` ke URL Vercel tanpa slash akhir.
