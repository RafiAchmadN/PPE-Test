<?php

namespace App\Console\Commands;

use Illuminate\Console\Command;

class FetchCuacaBmkg extends Command
{
    /**
     * The name and signature of the console command.
     *
     * @var string
     */
    protected $signature = 'bmkg:fetch-surabaya';

    /**
     * The console command description.
     *
     * @var string
     */
    protected $description = 'Menarik data prakiraan cuaca 31 Kecamatan Surabaya dari API BMKG';

    /**
     * Execute the console command.
     */
    public function handle()
    {
        $this->info("Mulai menarik data dari BMKG...");
        $this->line("====================================");

        // 1. Array 31 Kecamatan Surabaya beserta representasi kode adm4 (Kelurahan)
        $kecamatan_surabaya = [
            'Asemrowo' => '35.78.28.1001',
            'Benowo' => '35.78.19.1001',
            'Bubutan' => '35.78.13.1001',
            'Bulak' => '35.78.29.1001',
            'Dukuh Pakis' => '35.78.21.1001',
            'Gayungan' => '35.78.22.1001',
            'Genteng' => '35.78.07.1001',
            'Gubeng' => '35.78.08.1001',
            'Gunung Anyar' => '35.78.25.1001',
            'Jambangan' => '35.78.23.1001',
            'Karang Pilang' => '35.78.01.1001',
            'Kenjeran' => '35.78.17.1001',
            'Krembangan' => '35.78.15.1001',
            'Lakarsantri' => '35.78.18.1001',
            'Mulyorejo' => '35.78.26.1001',
            'Pabean Cantian' => '35.78.12.1001',
            'Pakal' => '35.78.30.1001',
            'Rungkut' => '35.78.03.1001',
            'Sambikerep' => '35.78.31.1001',
            'Sawahan' => '35.78.06.1001',
            'Semampir' => '35.78.16.1001',
            'Simokerto' => '35.78.11.1001',
            'Sukolilo' => '35.78.09.1001',
            'Sukomanunggal' => '35.78.27.1001',
            'Tambaksari' => '35.78.10.1001',
            'Tandes' => '35.78.14.1001',
            'Tegalsari' => '35.78.05.1001',
            'Tenggilis Mejoyo' => '35.78.24.1001',
            'Wiyung' => '35.78.20.1001',
            'Wonocolo' => '35.78.02.1001',
            'Wonokromo' => '35.78.04.1001'
        ];

        $hasil_tarikan = [];

        // Inisialisasi cURL
        $ch = curl_init();
        curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
        curl_setopt($ch, CURLOPT_SSL_VERIFYPEER, false); 

        $nomor = 1;
        foreach ($kecamatan_surabaya as $nama_kecamatan => $kode_adm4) {
            
            $url = "https://api.bmkg.go.id/publik/prakiraan-cuaca?adm4=" . $kode_adm4;
            curl_setopt($ch, CURLOPT_URL, $url);
            
            // Eksekusi API
            $response = curl_exec($ch);
            $dataBmkg = json_decode($response, true);
            
            // Pengecekan apakah format balikan JSON sesuai dan datanya ada
            if (isset($dataBmkg['data'][0]['cuaca'][0][0])) {
                $cuaca_saat_ini = $dataBmkg['data'][0]['cuaca'][0][0];
                
                $hasil_tarikan[] = [
                    'kecamatan'   => $nama_kecamatan,
                    'suhu'        => $cuaca_saat_ini['t'],             // Suhu (°C)
                    'kelembapan'  => $cuaca_saat_ini['hu'],            // Kelembapan (%)
                    'angin'       => $cuaca_saat_ini['ws'],            // Kecepatan Angin (km/jam)
                    'arah_angin'  => $cuaca_saat_ini['wd'],            // Arah Angin
                    'kondisi'     => $cuaca_saat_ini['weather_desc'],  // Kondisi (Cerah/Hujan)
                    'waktu_lokal' => $cuaca_saat_ini['local_datetime'] // Jam prediksi
                ];
                
                // Gunakan $this->info() bawaan Laravel untuk teks warna hijau di terminal
                $this->info("[$nomor/31] Sukses mengambil data Kecamatan $nama_kecamatan.");
            } else {
                // Gunakan $this->error() bawaan Laravel untuk teks warna merah di terminal
                $this->error("[$nomor/31] GAGAL mengambil data Kecamatan $nama_kecamatan.");
            }
            
            $nomor++;
            
            // Jeda 1 detik antar request agar tidak kena blokir
            sleep(1); 
        }

        curl_close($ch);

        $this->line("====================================");
        $this->info("Proses Selesai! Berikut cuplikan datanya:");
        
        // Menampilkan hasil JSON ke terminal
        $this->line(json_encode($hasil_tarikan, JSON_PRETTY_PRINT));
    }
}