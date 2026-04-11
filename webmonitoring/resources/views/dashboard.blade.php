<x-app-layout>
    @forelse($datas as $data)
    <div id="modal_{{$data->id}}" class="modal">
      <span id="close_{{$data->id}}" class="close">×</span>
      <img class="modal-content" id="image_{{$data->id}}" />
      <div id="text_{{$data->Bukti}}" style="  margin: auto;
                            display: block;
                            width: 80%;
                            max-width: 700px;
                            text-align: center;
                            color: white;
                            padding: 10px 0;
                            height: 150px;"> {{$data->Bukti}}</div>
    </div>
    @empty
        <div class="alert alert-danger">
            Data Monitoring belum Tersedia.
        </div>
    @endforelse
    
    @forelse($datas as $data)
    <div id="modal_2{{$data->id}}" class="modal">
      <span id="close_2{{$data->id}}" class="close">×</span>
      <img class="modal-content" id="image_2{{$data->id}}" />
      <div id="text_2{{$data->Bukti}}" style="  margin: auto;
                            display: block;
                            width: 80%;
                            max-width: 700px;
                            text-align: center;
                            color: white;
                            padding: 10px 0;
                            height: 150px;"> {{$data->Bukti}}</div>
    </div>
    @empty
    @endforelse

    <div class="py-12">
      <div class="max-w-7xl mx-auto sm:px-6 lg:px-8">
        
        <div class="rounded p-4 mb-4 shadow bg-white" style="color: black;max-width:20rem">
                <p class="font-weight-bold" >Total Pelanggaran</p>
                <!-- Mulai For Loop untuk Camera dari Div ini  -->
                @foreach($cameraCounts as $camera => $count)
                <div class="d-flex" style="gap: 8px;">
                  <span>{{ $camera }}:</span>
                  <span>{{ $count }}</span>
                </div>
                @endforeach
        </div>
        
        <!-- <div style="font-size: 1.2em; font-weight:bold" class="mb-2">Tabel Monitoring</div> -->
        <!-- <div class="bg-white overflow-hidden table-box shadow-sm sm:rounded-lg">
          <div class="p-2 date-box" >
                    <form id="dateForm" class="date-form">
                        <div class="flex" style="gap: 16px">
                            <div class="date-input">
                                <label for="start_date" class="m-0">Start date: </label>
                                <input type="date" name="start_date" />
                            </div>
                            <div class="date-input">
                                <label for="end_date" class="m-0">End date: </label>
                                <input type="date" name="end_date" />
                            </div>
                        </div>
                        
                        <div>
                            <button type="submit" class="apply-btn shadow-none">Apply</button>
                        </div>

                    </form>
            </div>
           -->
          <table class="table table-hover mb-0">
              <thead>
                <tr>
                  <th scope="col">ID</th>
                  <th scope="col">TANGGAL</th>
                  <th scope="col">WAKTU</th>
                  <th scope="col">Lokasi</th>
                  <th scope="col" class="text-center">Bukti Terdeteksi</th>
                  <th scope="col" class="text-center">Bukti</th>
                </tr>
              </thead>
              <tbody class="">
                @forelse ($datas as $data)
                  <tr>
                      <td>{{ $data->id }}</td>
                      <td>{{ $data->Tanggal }}</td>
                      <td>{{ $data->Waktu }}</td>
                      <td>{{ $data->Lokasi }}</td>
                      </td>
                      <td class="d-flex justify-content-center">
                          <img id="{{$data->id}}" 
                       class="img-bukti rounded max-w-[200px]" 
                       src="{{ asset('foto/' . $data->Bukti) }}" 
                       onclick="deployModal({{$data->id}})"
                       /></td>
                      <td class="justify-center">
                          <img id="2{{$data->id}}" 
                       class="img-bukti rounded max-w-[200px]" 
                       src="{{ asset('asli/' . $data->Bukti) }}" 
                       onclick="deployModal(2{{$data->id}})"
                       />
                  </tr>
                @empty
                    <div class="alert alert-danger">
                      Data Monitoring belum Tersedia.
                    </div>
                @endforelse
              </tbody>
          </table>  
          <div class="pl-2">{{ $datas->links() }}</div>
        </div> 
      </div>
    </div>
</x-app-layout>
