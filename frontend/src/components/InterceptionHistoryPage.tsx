import React, { useState, useEffect } from 'react';
import {
  ArrowLeft, CheckCircle2, RotateCcw, Trash2,
  Search, Download, AlertTriangle
} from 'lucide-react';
import { DownedDroneDetailed } from '../types';
import { Button, Badge } from './ui';
import s from './InterceptionHistoryPage.module.css';

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
    <div className={s.page}>
      <div className={s.head}>
        <div className={s.headL}>
          <Button variant="default" onClick={onBackToMap} title="Назад на тактичну карту">
            <ArrowLeft size={16} /> ТАКТИЧНА КАРТА
          </Button>
          <h1 className={s.title}>
            <span className={s.titleIco}><CheckCircle2 size={24} /></span>
            ЖУРНАЛ БОЙОВОЇ РОБОТИ ТА ЗБИТИХ ДРОНІВ
          </h1>
        </div>
        <div className={s.actions}>
          <Button variant="default" onClick={handleExportCSV} disabled={history.length === 0}>
            <Download size={14} /> Експорт у CSV
          </Button>
          <Button variant="default" onClick={fetchHistory} title="Оновити дані">
            <RotateCcw size={15} />
          </Button>
          <Button variant="danger" onClick={handleClearHistory} title="Очистити всю історію">
            <Trash2 size={15} /> Очистити журнал
          </Button>
        </div>
      </div>
      <div className={s.stats}>
        <div className={s.stat}>
          <div className={s.statT}>ВСЬОГО ЗБИТО ДРОНІВ</div>
          <div className={`${s.statV} ${s.vDanger}`}>{history.length}</div>
          <div className={s.statD}>Зафіксовано системою РЕБ</div>
        </div>
        <div className={s.stat}>
          <div className={s.statT}>УТИЛІЗОВАНО В KILLBOX</div>
          <div className={`${s.statV} ${s.vSafe}`}>{killboxInterceptions}</div>
          <div className={s.statD}>Хірургічний зрив над безпечними зонами</div>
        </div>
        <div className={s.stat}>
          <div className={s.statT}>ЕФЕКТИВНІСТЬ БЕЗПЕКИ</div>
          <div className={`${s.statV} ${s.vInfo}`}>
            {history.length > 0 ? `${Math.round((killboxInterceptions / history.length) * 100)}%` : '100%'}
          </div>
          <div className={s.statD}>Частка падінь поза населеними пунктами</div>
        </div>
      </div>
      <div className={s.filter}>
        <div className={s.searchWrap}>
          <Search size={16} className={s.searchIco} />
          <input
            type="text"
            placeholder="Швидкий пошук за номером борта (SHAHED-...), об'єктом атаки, комплексом РЕБ або зоною падіння..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className={s.search}
          />
        </div>
      </div>
      <div className={s.tableWrap}>
        {loading ? (
          <div className={s.empty}>Завантаження бойового журналу...</div>
        ) : filtered.length === 0 ? (
          <div className={s.empty}>
            <AlertTriangle size={32} />
            <div>Записів про збиті дрони не знайдено</div>
          </div>
        ) : (
          <table className={s.table}>
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
                <th className={s.center}>Дія</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((row) => (
                <tr key={row.id}>
                  <td><strong className={s.id}>{row.drone_id}</strong></td>
                  <td className={s.dim}>{row.spawn_time}</td>
                  <td className={s.hl}>{row.downed_time}</td>
                  <td className={s.mono}>{row.spawn_coords}</td>
                  <td><b className={s.tgt}>{row.target_name}</b></td>
                  <td><span className={s.ew}>{row.interceptor_name}</span></td>
                  <td className={s.mono}>{row.crash_coords}</td>
                  <td>
                    <span className={row.crash_zone.includes('🟢') ? s.safe : row.crash_zone.includes('🔴') ? s.zoneDanger : undefined}>
                      {row.crash_zone}
                    </span>
                  </td>
                  <td>
                    <Badge tone="danger">💥 {row.status}</Badge>
                  </td>
                  <td className={s.center}>
                    <Button
                      variant="danger"
                      onClick={() => handleDeleteItem(row.id)}
                      title="Видалити запис"
                    >
                      <Trash2 size={13} />
                    </Button>
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
