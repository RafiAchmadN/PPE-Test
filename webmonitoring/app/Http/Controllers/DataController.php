<?php

namespace App\Http\Controllers;

//return type View
use Illuminate\View\View;

use Illuminate\Http\Request;
use App\Models\Data;
class DataController extends Controller
{
    public function index(): View
    {
        //get posts
        $datas = Data::latest()->paginate(5);

        // Count occurrences of each camera type
        $cameraCounts = Data::select('Lokasi', \DB::raw('count(*) as total'))
        ->groupBy('Lokasi')
        ->pluck('total', 'Lokasi');


        //render view with posts
        return view('dashboard', compact('datas', 'cameraCounts'));
    }
}
