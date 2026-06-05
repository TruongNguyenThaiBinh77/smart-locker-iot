import { useState, useEffect } from 'react';
import { Monitor, Shield, LayoutDashboard, Settings, Package, Activity, LogOut } from 'lucide-react';
import KioskScreen from './screens/KioskScreen';
import AdminScreen from './screens/AdminScreen';

export default function App() {
  const [tab, setTab] = useState('kiosk');
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
        {/* ─── Sidebar ─── */}
        <div className="sidebar">
          <div className="sidebar-section-label">Màn hình Kiosk</div>
          <div className={`nav-item ${tab === 'kiosk' ? 'active' : ''}`} onClick={() => setTab('kiosk')}>
            <Monitor size={16} />
            <div className="nav-label">Khách hàng UI</div>
          </div>
          
          <div className="sidebar-divider"></div>
          
          <div className="sidebar-section-label">Hệ thống</div>
          <div className={`nav-item ${tab === 'admin' ? 'active' : ''}`} onClick={() => setTab('admin')}>
            <LayoutDashboard size={16} />
            <div className="nav-label">Admin Dashboard</div>
          </div>
        </div>

        {/* ─── Main View ─── */}
        <div className="main-content">
          {tab === 'kiosk' && <KioskScreen />}
          {tab === 'admin' && <AdminScreen />}
        </div>
      </div>
    </div>
  );
}
