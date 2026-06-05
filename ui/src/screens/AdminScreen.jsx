import { useState, useEffect } from 'react';
import * as api from '../api';
import { RefreshCw, Box, Activity, Settings, Terminal, ShieldCheck } from 'lucide-react';

export default function AdminScreen() {
  const [sysInfo, setSysInfo] = useState(null);
  const [sysState, setSysState] = useState(null);
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchData = async () => {
    try {
      const [infoRes, stateRes, logRes] = await Promise.all([
        api.getSystemInfo(),
        api.getSystemState(),
        api.getRecentLogs(20)
      ]);
      setSysInfo(infoRes);
      setSysState(stateRes);
      setLogs(logRes.logs || []);
    } catch (e) {
      console.error('Failed to fetch admin data', e);
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchData();
    const timer = setInterval(fetchData, 3000);
    return () => clearInterval(timer);
  }, []);

  if (loading && !sysInfo) {
    return (
      <div className="dashboard-scroll" style={{ alignItems: 'center', justifyContent: 'center' }}>
        <RefreshCw size={24} className="spinner" style={{ color: 'var(--accent)' }} />
      </div>
    );
  }

  const cabinets = sysState?.cabinets || {};
  const activeCabinetIds = Object.keys(cabinets);

  return (
    <div className="dashboard-scroll">
      <div className="stats-row">
        <div className="stat-card blue">
          <div className="stat-card-num">{activeCabinetIds.length}</div>
          <div className="stat-card-lbl">CABINETS</div>
        </div>
        <div className="stat-card green">
          <div className="stat-card-num">{Object.values(cabinets).reduce((sum, c) => sum + Object.keys(c.lockers || {}).length, 0)}</div>
          <div className="stat-card-lbl">TỔNG SỐ Ô TỦ</div>
        </div>
        <div className="stat-card orange">
          <div className="stat-card-num">{logs.length}</div>
          <div className="stat-card-lbl">LOGS (Gần nhất)</div>
        </div>
      </div>

      <div className="card">
        <div className="card-title">
          <Box size={14} style={{ marginRight: 6, verticalAlign: -2 }} />
          Trạng thái Tủ (Realtime)
        </div>
        {activeCabinetIds.length === 0 ? (
          <div style={{ padding: 20, textAlign: 'center', color: 'var(--text-muted)' }}>Chưa có cabinet nào kết nối</div>
        ) : (
          activeCabinetIds.map(cabId => {
            const cab = cabinets[cabId];
            const lockers = cab.lockers || {};
            return (
              <div key={cabId} style={{ marginBottom: 16 }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
                  Cabinet: <span style={{ color: 'var(--accent)' }}>{cabId}</span>
                  <span className={`status-pill ${cab.status === 'online' ? 'online' : 'offline'}`} style={{ marginLeft: 8 }}>
                    <div className={`dot ${cab.status === 'online' ? 'green' : 'red'}`}></div> {cab.status}
                  </span>
                </div>
                <div className="locker-grid">
                  {Object.keys(lockers).sort((a,b) => parseInt(a)-parseInt(b)).map(lId => {
                    const l = lockers[lId];
                    const isOpening = l.is_opening;
                    const isClosed = l.door_status === 'closed';
                    let cls = isOpening ? 'opening' : (isClosed ? 'closed' : 'offline');
                    
                    return (
                      <div key={lId} className={`locker-cell ${cls}`}>
                        <div className="locker-cell-id">Ô {lId}</div>
                        <div>{isOpening ? 'Opening' : (isClosed ? 'Đóng' : 'Mở')}</div>
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })
        )}
      </div>

      <div className="card">
        <div className="card-title">
          <Terminal size={14} style={{ marginRight: 6, verticalAlign: -2 }} />
          Recent Logs (MQTT & API)
        </div>
        <div style={{ maxHeight: 200, overflowY: 'auto' }}>
          <table className="log-table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Dir</th>
                <th>Topic / Event</th>
                <th>Payload</th>
              </tr>
            </thead>
            <tbody>
              {logs.map((log, i) => (
                <tr key={i}>
                  <td style={{ whiteSpace: 'nowrap' }}>{new Date(log.timestamp * 1000).toLocaleTimeString()}</td>
                  <td>
                    <span className={`log-dir ${log.direction === 'in' ? 'in' : 'out'}`}>{log.direction.toUpperCase()}</span>
                  </td>
                  <td>{log.topic}</td>
                  <td style={{ wordBreak: 'break-all', fontFamily: 'monospace' }}>
                    {typeof log.payload === 'object' ? JSON.stringify(log.payload) : log.payload}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
