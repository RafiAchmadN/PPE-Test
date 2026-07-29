import { useEffect, useState } from 'react';
import * as api from '../lib/api';

export default function Topbar() {
  const [clock, setClock] = useState('');
  const [serverAddr, setServerAddr] = useState('');

  useEffect(() => {
    const tick = () =>
      setClock(
        new Date().toLocaleString('en-GB', {
          day: '2-digit',
          month: 'short',
          year: 'numeric',
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
        })
      );
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    api
      .getInfo()
      .then((d) => setServerAddr(d?.access_url || ''))
      .catch(() => {});
  }, []);

  return (
    <div className="h-14 flex items-center justify-between px-7 bg-base-100 border-b border-base-300 flex-shrink-0">
      <h1 className="text-lg font-semibold flex items-center gap-2.5 text-base-content">
        <img src="/heti-icon.png" alt="" className="h-[22px] w-[22px] object-contain bg-white rounded p-0.5 flex-shrink-0" />
        <span className="inline-block w-2 h-2 rounded-full bg-success animate-pulse"></span>
        PPE Monitoring System
      </h1>
      <div className="flex items-center gap-5">
        {serverAddr && (
          <span className="text-[11px] text-base-content/40 font-mono-app" title="Alamat akses jaringan lokal">
            📡 {serverAddr}
          </span>
        )}
        <span className="text-xs text-base-content/40 font-mono-app">{clock}</span>
      </div>
    </div>
  );
}
