# Project Standard — FreshCheck

> Dibuat dari catatan "[21] Global AI Hackathon" (dokumen "Lets Us Cooked"). Dokumen ini adalah spesifikasi project yang siap dieksekusi oleh AI CLI (mis. Claude Code) untuk membangun prototipe hackathon.

## 1. Ringkasan Kompetisi

- **Nama kompetisi:** Global AI Hackathon (Geek Room)
- **Link pendaftaran/hackathon:** https://hackculture.io/hackathons/ai-global-hackathon
- **Akun hackathon (dipakai bersama tim):**
  - Email: `fikridhan4@gmail.com`
  - Password: `#Aliria1234`
- **Catatan deadline (ada dua referensi berbeda di dokumen sumber, perlu dikonfirmasi ulang ke panitia):**
  - Folder catatan mencantumkan deadline **30 November 2026**
  - Baris "Dl Submit Project" di isi tab mencantumkan **21 November 2026**
  - ⚠️ Karena ada dua tanggal berbeda, segera cek ulang tanggal resmi di halaman hackathon sebelum submit.
- **Status problem statement:** Live — problem statement tayang mulai 1 Nov, window submission prototipe dibuka bersamaan, dengan masa pengerjaan dua minggu.
- **Setiap anggota tim wajib membuat akun di AI Global Hackathon + melakukan registrasi lomba terlebih dahulu** sebelum submit.

## 2. Ide Project Terpilih: "FreshCheck"

**FreshCheck** adalah *stale-claim detector* untuk jawaban LLM — sistem yang mendeteksi klaim/fakta dalam jawaban AI yang sudah usang (basi) dan memverifikasinya ulang terhadap sumber web terkini.

- **Kategori:** AI Agents & Intelligent Systems
- **Problem statement acuan:** Problem Statement #6 — *"Build a Stale-Answer Detector for AI Applications"* (kombinasi Tavily + Bifrost)

### 2.1 Masalah (Problem)
Jawaban LLM soal harga, versi API, regulasi, atau fakta perusahaan diam-diam menjadi usang begitu realita di baliknya berubah — dan pengguna tidak punya sinyal bagian mana dari jawaban yang perlu dicek ulang.

### 2.2 Target Pengguna
Tim yang men-ship produk berbasis LLM (support bot, internal tools) yang butuh sinyal kepercayaan ringan sebelum jawaban sampai ke pengguna/customer.

### 2.3 Solusi yang Diusulkan
1. Jawaban yang dihasilkan LLM dilewatkan ke **claim extractor** — sebuah LLM call yang dirutekan lewat **Bifrost** (murah/cepat, provider-agnostic, mudah ditukar model) untuk menarik klaim faktual yang bisa dicek (harga, nomor versi, nama regulasi, tanggal).
2. Setiap klaim diverifikasi ulang dengan **Tavily Search** yang ditarget.
3. Setiap klaim diberi **freshness score**: `confirmed current` / `contradicted` / `unverifiable`, lengkap dengan sumber kontradiksi (link) yang ditautkan.
4. Hasil verifikasi per-klaim dilampirkan kembali ke jawaban asli.

### 2.4 Kenapa Ini Penting
Fitur ini menyasar failure mode nyata yang masih kurang diperhatikan: **jawaban AI yang percaya diri tapi salah** — bukan sekadar "accuracy checker" generik.

### 2.5 Nilai Pembeda (Innovation/Differentiation)
Scoring dilakukan **per-klaim**, bukan per-jawaban, dengan sitasi sumber yang terlihat untuk setiap kontradiksi. Satu angka ringkasan seperti "confidence: 72%" sengaja dihindari karena kurang berguna dibanding breakdown per klaim.

### 2.6 Tech Stack yang Disarankan
- **Bifrost** — merutekan LLM call untuk ekstraksi klaim; provider-agnostic sehingga tim bisa tukar model demi kecepatan/biaya saat demo.
- **Tavily Search/Extract API** — re-verifikasi klaim terhadap sumber web live.
- Kombinasi ini sengaja dipakai karena problem statement ini memang dirancang untuk mewajibkan dua teknologi sponsor sekaligus (Bifrost + Tavily), yang kemungkinan besar akan dihargai lebih oleh juri.

### 2.7 Kelayakan (Feasibility)
Tinggi — untuk scope klaim 3–4 kategori (harga, versi, tanggal, entitas bernama). **Fact-checking open-domain penuh di luar scope** untuk window pengerjaan dua minggu dan sebaiknya tidak dicoba.

### 2.8 Risiko Utama & Mitigasi
| Risiko | Mitigasi |
|---|---|
| False positive pada klaim yang sifatnya subjektif/sulit diverifikasi | Tambahkan bucket ketiga `unverifiable`, jangan hanya `confirmed`/`contradicted` |
| Hasil pencarian Tavily sendiri basi/kualitas rendah | Beri bobot lebih ke sumber resmi/primary source, tampilkan tanggal publish sumber di samping verdict |

### 2.9 Opsi Integrasi Tavily Tambahan (dari form submission)
Form registrasi menanyakan apakah project juga mengintegrasikan problem statement Tavily lain. Opsi yang tersedia (pilih salah satu atau keduanya — perlu diputuskan tim):
- Pre-Meeting Briefing Agent
- Stale-Answer Detector *(ini yang jadi fokus utama FreshCheck)*

## 3. Daftar Lengkap Problem Statement (Konteks Kompetisi)

Tema besar semua problem statement: **AI Agents & Intelligent Systems**.

### Bifrost Problem Statements
1. **Build a Coding Agent That Gets the Job Done on the Fewest Tokens** — AI coding agent yang menyelesaikan tugas development nyata sambil meminimalkan konsumsi token & biaya operasional; harus tetap jalan saat provider outage, menegakkan limit spending individu, melindungi repo rahasia dengan local model, dan minta approval user sebelum aksi berisiko (file write, shell command, Git action).
2. **Build a Benchmarking Platform for AI Agents, Not Just Models** — platform benchmarking framework-independent yang menguji AI agent pada task identik; mengukur task success, execution steps, tool calls, token usage, cost, completion time lintas percobaan berulang, termasuk perilaku saat tool gagal/model tidak tersedia/instruksi menyesatkan.
3. **Build an Agent That Pentests a Target on Its Own** — AI agent otonom untuk pentest berizin di lingkungan lab terisolasi; menjelajah target yang diizinkan, menafsirkan hasil, memutuskan langkah berikutnya secara independen, menghasilkan laporan keamanan yang actionable (temuan, bukti, severity, rekomendasi perbaikan).
4. **Open-Source Bifrost Gateway** — memperluas gateway open-source Bifrost dengan fitur praktis (plugin, integrasi provider, caching/routing, UI, atau dev tool) yang layak jadi pull request upstream, lengkap dokumentasi dan test.

### Tavily Problem Statements
5. **Tavily Research Agent** — agent riset yang menyiapkan briefing satu halaman sebelum meeting, berdasarkan perkembangan 30 hari terakhir (hire baru, update penting) dari perusahaan/orang terkait, lengkap sumber, poin diskusi, dan pertanyaan.
6. **Build a Stale-Answer Detector for AI Applications** — *(dipilih tim sebagai "FreshCheck", lihat Bagian 2)*.

## 4. Ketentuan Submission (Problem Statements & Prototype Submission)

Status: **Live**. Baca penuh sebelum submit.

1. Problem statement tayang 1 Nov; window submission prototipe dibuka bersamaan; kerjakan dalam **dua minggu**.
2. Pilih problem statement utama dari dropdown Theme.
3. Project boleh dibangun pakai Bifrost, Tavily, atau keduanya. Boleh submit 2 project terpisah untuk 2 teknologi.
4. Jika project gabungan (Bifrost + Tavily): pilih challenge Bifrost sebagai problem statement utama, centang checkbox "Tavily integration" untuk challenge tambahan.
5. Jika hanya project Tavily: pilih problem statement Tavily sebagai tema utama. Jika submit untuk kedua teknologi, isi form submission secara lengkap untuk kedua project.
6. **Repo GitHub wajib publik**, dengan README detail (langkah instalasi, implementasi, teknologi yang dipakai).
7. **Pitch deck** menjelaskan problem, solusi, arsitektur teknis, dan working prototype. Jika menggabungkan dua teknologi, tunjukkan kontribusi masing-masing dengan jelas.
8. Deployed application **tidak wajib**, tapi live demo atau video demonstrasi sangat disarankan.

### Checklist Form Pengumpulan (Global AI Hackathon)
- [ ] Project title
- [ ] Theme
- [ ] Problem statement
- [ ] Link GitHub project
- [ ] Link video demo
- [ ] File PPT (pitch deck)
- [ ] Jawab: apakah juga mengintegrasikan problem statement Tavily lain? (centang semua atau pilih salah satu: Pre-Meeting Briefing Agent / Stale-Answer Detector)

## 5. Resource Resmi (Geek Room Global AI Hackathon Resources)

| # | Resource | URL | Keterangan |
|---|---|---|---|
| 1 | Bifrost GitHub Repository | https://github.com/maximhq/bifrost | Gateway AI open-source Bifrost: instalasi, model routing, provider, contoh |
| 2 | Bifrost Documentation | https://docs.getmaxim.ai | Setup Bifrost, konfigurasi model provider, fitur gateway untuk AI agent app |
| 3 | Tavily API Documentation | https://docs.tavily.com | Integrasi search/research API Tavily: endpoint, auth, contoh, panduan implementasi |
| 4 | Claim Your Tavily API Credits | https://app.tavily.com/home | Klaim 8.000 kredit Tavily API dengan kode kupon `GEEKROOM2`; redeem sebelum **28 November 2026** |
| 5 | Hackathon Problem Statements | https://hackculture.io/hackathons/ai-global-hackathon | Lihat 6 problem statement lengkap (4 Bifrost + 2 Tavily) |

## 6. Rencana Eksekusi untuk AI CLI

Gunakan dokumen ini sebagai spesifikasi awal saat menjalankan AI CLI (mis. Claude Code) untuk mulai membangun FreshCheck. Urutan kerja yang disarankan:

1. **Setup repo & environment**
   - Inisialisasi repo publik (sesuai syarat submission).
   - Daftar akun & klaim Tavily credits (kode `GEEKROOM2`) sebelum 28 Nov 2026.
   - Setup Bifrost gateway lokal/cloud sesuai dokumentasi (resource #1–#2).
2. **Bangun claim extractor**
   - LLM call via Bifrost untuk menarik klaim faktual (harga, versi, tanggal, regulasi, entitas) dari teks jawaban LLM input.
3. **Bangun re-verification layer**
   - Untuk setiap klaim, jalankan targeted search via Tavily API.
   - Tentukan status: `confirmed current` / `contradicted` / `unverifiable`, simpan link sumber kontradiksi.
4. **Bangun freshness scoring & output**
   - Tampilkan hasil per-klaim (bukan skor tunggal), lengkap sitasi sumber dan tanggal publish sumber.
5. **Bangun demo interface minimal**
   - Input: jawaban LLM mentah. Output: jawaban beranotasi dengan status freshness per klaim.
6. **Siapkan deliverable submission**
   - README lengkap (instalasi, implementasi, tech stack).
   - Pitch deck (problem, solusi, arsitektur, prototype, kontribusi Bifrost+Tavily).
   - Video demo / live demo (opsional tapi disarankan).
7. **Isi form submission** sesuai checklist Bagian 4.

## 7. Hal yang Perlu Diputuskan Tim

- [ ] Konfirmasi deadline final (21 Nov vs 30 Nov 2026) ke panitia/halaman resmi hackathon.
- [ ] Putuskan apakah juga mengerjakan problem statement Tavily kedua (Pre-Meeting Briefing Agent) sebagai integrasi tambahan, atau fokus penuh ke Stale-Answer Detector.
- [ ] Bagi role tim (siapa pegang Bifrost integration, siapa pegang Tavily integration, siapa pegang UI/demo, siapa pegang pitch deck).