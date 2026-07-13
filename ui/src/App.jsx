import { useState, useEffect } from 'react';
import { Monitor } from 'lucide-react';
import KioskScreen from './screens/KioskScreen';

export default function App() {
  const [time, setTime] = useState(new Date());

  useEffect(() => {
    const timer = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  const timeStr = time.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' });
  const dateStr = time.toLocaleDateString('vi-VN', { day: '2-digit', month: '2-digit', year: 'numeric' });

  return (
    <div className="app-shell">
      {/* ─── Header ─── */}
      <div className="top-bar">
        <div className="top-bar-brand">
          <Monitor size={18} /> Lock.R IoT
        </div>
        <div className="top-bar-status">
          <div className="status-pill online">
            <div className="dot green"></div> Online
          </div>
          <div className="top-bar-clock">
            {timeStr} • {dateStr}
          </div>
        </div>
      </div>

      <div className="layout">
        {/* ─── Main View ─── */}
        <div className="main-content">
          <KioskScreen />
        </div>
      </div>
    </div>
  );
}
