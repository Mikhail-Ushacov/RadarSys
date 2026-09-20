// frontend/src/components/InterceptionHistoryPage.tsx
import React, { useState, useEffect } from 'react';
import { 
  ArrowLeft, CheckCircle2, RotateCcw, Trash2, 
  Search, ShieldAlert, Crosshair, Download, AlertTriangle
} from 'lucide-react';
import { DownedDroneDetailed } from '../types';

interface Props {
  onBackToMap: () => void;
}

export const InterceptionHistoryPage: React.FC<Props> = ({ onBackToMap }) => {
  const [history, setHistory] = useState<DownedDroneDetailed[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const backendUrl = `http://${window.location.hostname}:8000`;

  const fetchHistory = async () => {
    try {
      setLoading(true);
      const res = await fetch(`${backendUrl}/api/v1/downed_drones`);
      const data = await res.json();
      setHistory(data || []);
    } catch (err) {
      console.error('Помилка завантаження журналу:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchHistory();
  }, []);

  const handleClearHistory = async () => {
    if (!window.confirm('Ви впевнені, що хочете очистити весь журнал збитих дронів?')) return;
    await fetch(`${backendUrl}/api/v1/downed_drones`, { method: 'DELETE' });
    setHistory([]);
  };

  const handleDeleteItem = async (id: number) => {
    await fetch(`${backendUrl}/api/v1/downed_drones/${id}`, { method: 'DELETE' });
    setHistory((prev) => prev.filter((item) => item.id !== id));
  };

  const handleExportCSV = () => {
    if (history.length === 0) return;
    const headers = ["ID", "Бортовий номер", "Час появи", "Час збиття", "Координати появи", "Ціль ворога", "Комплекс РЕБ", "Координати падіння", "Сектор падіння", "Статус"];
    const rows = history.map((d) => [
      d.id,
      d.drone_id,
      `"${d.spawn_time}"`,
      `"${d.downed_time}"`,
      `"${d.spawn_coords}"`,
      `"${d.target_name}"`,
      `"${d.interceptor_name}"`,
      `"${d.crash_coords}"`,
      `"${d.crash_zone}"`,
      d.status
    ]);
    const csvContent = "data:text/csv;charset=utf-8,\uFEFF" + [headers.join(","), ...rows.map((e) => e.join(","))].join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `EW_Interception_Log_${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const filtered = history.filter((d) => 
    d.drone_id.toLowerCase().includes(searchTerm.toLowerCase()) ||
    d.target_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    d.interceptor_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    d.crash_zone.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const killboxInterceptions = history.filter((h) => h.crash_zone.includes('🟢') || h.crash_zone.toLowerCase().includes('killbox')).length;

  return (
    <div className="history-page-container">
      {/* Header */}
      <div className="history-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <button onClick={onBackToMap} className="btn-back" title="Назад на тактичну карту">
            <ArrowLeft size={16} /> ТАКТИЧНА КАРТА
          </button>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <CheckCircle2 size={24} color="#10b981" />
            <h1 className="history-title">ЖУРНАЛ БОЙОВОЇ РОБОТИ ТА ЗБИТИХ ДРОНІВ</h1>
          </div>
        </div>

        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <button onClick={handleExportCSV} className="btn-export" disabled={history.length === 0}>
            <Download size={14} /> Експорт у CSV
          </button>
          <button onClick={fetchHistory} className="btn-icon-action" title="Оновити дані">
            <RotateCcw size={15} />
          </button>
          <button onClick={handleClearHistory} className="btn-danger-action" title="Очистити всю історію">
            <Trash2 size={15} /> Очистити журнал
          </button>
        </div>
      </div>

      {/* Статистичні картки */}
      <div className="history-stats-grid">
        <div className="stat-card">
          <div className="stat-card-title">ВСЬОГО ЗБИТО ДРОНІВ</div>
          <div className="stat-card-val" style={{ color: '#ef4444' }}>{history.length}</div>
          <div className="stat-card-desc">Зафіксовано системою РЕБ</div>
        </div>
        <div className="stat-card">
          <div className="stat-card-title">УТИЛІЗОВАНО В KILLBOX</div>
          <div className="stat-card-val" style={{ color: '#10b981' }}>{killboxInterceptions}</div>
          <div className="stat-card-desc">Хірургічний зрив над безпечними зонами</div>
        </div>
        <div className="stat-card">
          <div className="stat-card-title">ЕФЕКТИВНІСТЬ БЕЗПЕКИ</div>
          <div className="stat-card-val" style={{ color: '#38bdf8' }}>
            {history.length > 0 ? `${Math.round((killboxInterceptions / history.length) * 100)}%` : '100%'}
          </div>
          <div className="stat-card-desc">Частка падінь поза населеними пунктами</div>
        </div>
      </div>

      {/* Пошуковий фільтр */}
      <div className="history-filter-bar">
        <div style={{ position: 'relative', flex: 1 }}>
          <Search size={16} color="#94a3b8" style={{ position: 'absolute', left: '12px', top: '11px' }} />
          <input
            type="text"
            placeholder="Швидкий пошук за номером борта (SHAHED-...), об'єктом атаки, комплексом РЕБ або зоною падіння..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="history-search-input"
          />
        </div>
      </div>

      {/* Таблиця історії */}
      <div className="history-table-container">
        {loading ? (
          <div style={{ padding: '3rem', textAlign: 'center', color: '#94a3b8' }}>Завантаження бойового журналу...</div>
        ) : filtered.length === 0 ? (
          <div style={{ padding: '3rem', textAlign: 'center', color: '#64748b' }}>
            <AlertTriangle size={32} style={{ marginBottom: '8px', opacity: 0.6 }} />
            <div>Записів про збиті дрони не знайдено</div>
          </div>
        ) : (
          <table className="history-table">
            <thead>
              <tr>
                <th>№ Борта</th>
                <th>Час появи</th>
                <th>Час збиття</th>
                <th>Координати появи</th>
                <th>Ціль атаки</th>
                <th>Комплекс РЕБ</th>
                <th>Точка падіння</th>
                <th>Сектор / Зона падіння</th>
                <th>Статус</th>
                <th style={{ textAlign: 'center' }}>Дія</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((row) => (
                <tr key={row.id}>
                  <td><strong style={{ color: '#f87171' }}>{row.drone_id}</strong></td>
                  <td style={{ color: '#94a3b8', fontSize: '0.75rem' }}>{row.spawn_time}</td>
                  <td style={{ color: '#38bdf8', fontSize: '0.75rem', fontWeight: 'bold' }}>{row.downed_time}</td>
                  <td style={{ fontFamily: 'monospace', fontSize: '0.75rem', color: '#cbd5e1' }}>{row.spawn_coords}</td>
                  <td><b style={{ color: '#fbbf24' }}>{row.target_name}</b></td>
                  <td><span style={{ color: '#a78bfa', fontWeight: 'bold' }}>{row.interceptor_name}</span></td>
                  <td style={{ fontFamily: 'monospace', fontSize: '0.75rem', color: '#cbd5e1' }}>{row.crash_coords}</td>
                  <td>
                    <span style={{ 
                      color: row.crash_zone.includes('🟢') ? '#34d399' : row.crash_zone.includes('🔴') ? '#f87171' : '#e2e8f0',
                      fontWeight: '500'
                    }}>
                      {row.crash_zone}
                    </span>
                  </td>
                  <td>
                    <span className="badge badge-danger">💥 {row.status}</span>
                  </td>
                  <td style={{ textAlign: 'center' }}>
                    <button 
                      onClick={() => handleDeleteItem(row.id)} 
                      className="btn-delete-row"
                      title="Видалити запис"
                    >
                      <Trash2 size={13} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};