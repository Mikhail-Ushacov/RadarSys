// frontend/src/components/HardTestPage.tsx
import React, { useState, useEffect } from 'react';
import {
  ArrowLeft, Flame, Play, Download, Search, ChevronDown, ChevronUp,
  Siren, Zap
} from 'lucide-react';
import { Button, Badge } from './ui';
import s from './HardTestPage.module.css';

interface Props {
  onBackToMap: () => void;
}

export const HardTestPage: React.FC<Props> = ({ onBackToMap }) => {
  const [isRunning, setIsRunning] = useState(false);
  const [progress, setProgress] = useState(0);
  const [statusMsg, setStatusMsg] = useState('Натисніть «СТАРТ ТЕСТУ» для запуску');
  const [summary, setSummary] = useState<any>(null);
  const [details, setDetails] = useState<any[]>([]);
  const [showDetails, setShowDetails] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');

  const backendUrl = `http://${window.location.hostname}:8000`;

  const pollStatus = async () => {
    try {
      const res = await fetch(`${backendUrl}/api/v1/hard_test/status`);
      const data = await res.json();
      setIsRunning(data.is_running);
      setProgress(data.progress);
      if (data.status_message) setStatusMsg(data.status_message);
      if (data.summary && Object.keys(data.summary).length > 0) {
        setSummary(data.summary);
      }
      if (!data.is_running && data.progress === 100) {
        fetchResults();
      }
    } catch (e) {
      console.error(e);
    }
  };

  const fetchResults = async () => {
    try {
      const res = await fetch(`${backendUrl}/api/v1/hard_test/results`);
      const data = await res.json();
      if (data.summary) setSummary(data.summary);
      if (data.detailed_results) setDetails(data.detailed_results);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    pollStatus();
    fetchResults();
  }, []);

  useEffect(() => {
    let timer: any;
    if (isRunning) {
      timer = setInterval(pollStatus, 800);
    }
    return () => clearInterval(timer);
  }, [isRunning]);

  const handleStartTest = async () => {
    setIsRunning(true);
    setProgress(5);
    setStatusMsg('Ініціалізація симуляційного пакету...');
    await fetch(`${backendUrl}/api/v1/hard_test/start`, { method: 'POST' });
  };

  const handleDownloadCsv = () => {
    window.open(`${backendUrl}/api/v1/hard_test/export_csv`, '_blank');
  };

  const filteredDetails = details.filter((d) => {
    const term = searchTerm.toLowerCase();
    return (
      d.drone_id.toLowerCase().includes(term) ||
      d.drone_type.toLowerCase().includes(term) ||
      d.crash_zone.toLowerCase().includes(term) ||
      d.interceptor_name.toLowerCase().includes(term)
    );
  });

  return (
    <div className={s.page}>
      <div className={s.head}>
        <div className={s.headL}>
          <Button variant="default" onClick={onBackToMap}>
            <ArrowLeft size={16} /> ТАКТИЧНА КАРТА
          </Button>
          <h1 className={s.title}>
            <span className={s.titleIco}><Flame size={24} /></span>
            HARD TEST: ПРИШВИДШЕНИЙ СТРЕС-ТЕСТ ІСТОРИЧНИМИ БПЛА
          </h1>
        </div>
        <div className={s.actions}>
          <Button
            variant="danger"
            onClick={handleStartTest}
            disabled={isRunning}
          >
            <Play size={14} /> {isRunning ? 'РОЗРАХУНОК ТРИВАЄ...' : 'СТАРТ HARD TEST'}
          </Button>
          <Button
            variant="default"
            onClick={handleDownloadCsv}
            disabled={details.length === 0}
          >
            <Download size={14} /> Експорт Hard Test (CSV)
          </Button>
        </div>
      </div>

      {/* ПРОГРЕС БАР */}
      <div className={s.progressBox}>
        <div className={s.progressRow}>
          <span>{statusMsg}</span>
          <span className="t-mono">{progress}%</span>
        </div>
        <div className={s.progressBarBg}>
          <div className={s.progressBarFill} style={{ width: `${progress}%` }} />
        </div>
      </div>

      {/* КОРОТКА АНАЛІТИКА СИМУЛЯЦІЇ */}
      {summary ? (
        <div className={s.statsGrid}>
          <div className={s.statCard}>
            <div className={s.statTitle}>ЕФЕКТИВНІСТЬ РЕБ</div>
            <div className={s.statValue} style={{ color: '#10b981' }}>
              {summary.efficiency_pct}%
            </div>
            <div className={s.statSub}>
              Збито {summary.downed_count} з {summary.total_tested} дронів
            </div>
          </div>

          <div className={s.statCard}>
            <div className={s.statTitle}>УТИЛІЗАЦІЯ В KILLBOX</div>
            <div className={s.statValue} style={{ color: '#38bdf8' }}>
              {summary.killbox_ratio_pct}%
            </div>
            <div className={s.statSub}>
              {summary.killbox_safe_count} у безпечних зелених зонах
            </div>
          </div>

          <div className={s.statCard}>
            <div className={s.statTitle}>ВИКЛИКІВ ДСНС / 112</div>
            <div className={s.statValue} style={{ color: summary.emergency_112_count > 0 ? '#ef4444' : '#10b981' }}>
              {summary.emergency_112_count}
            </div>
            <div className={s.statSub}>
              Уламки в буферних або житлових зонах
            </div>
          </div>

          <div className={s.statCard}>
            <div className={s.statTitle}>ЗАХИСТ ОБ'ЄКТІВ ОКІ</div>
            <div className={s.statValue} style={{ color: '#f59e0b' }}>
              {summary.ci_defended_count} / {summary.total_tested}
            </div>
            <div className={s.statSub}>
              Проривів рубежів: {summary.ci_breached_count}
            </div>
          </div>

          <div className={s.statCard}>
            <div className={s.statTitle}>СЕРЕДНІЙ ЧАС ЗРИВУ</div>
            <div className={s.statValue} style={{ color: '#a855f7' }}>
              {summary.avg_interception_time_sec} с
            </div>
            <div className={s.statSub}>
              З моменту засічки до утилізації
            </div>
          </div>

          <div className={s.statCard}>
            <div className={s.statTitle}>СЕРЕДНІЙ РОЗЛІТ УЛАМКІВ</div>
            <div className={s.statValue} style={{ color: '#f87171' }}>
              ~{summary.avg_debris_radius_m} м
            </div>
            <div className={s.statSub}>
              З урахуванням балістики та вітру
            </div>
          </div>
        </div>
      ) : (
        <div className={s.empty}>
          <Zap size={32} />
          <div>Натисніть «СТАРТ HARD TEST», щоб запустити розрахунок аналітики за реальними даними.</div>
        </div>
      )}

      {/* ПАНЕЛЬ ПЕРЕМИКАННЯ ДЕТАЛЬНОЇ ТАБЛИЦІ */}
      <div className={s.detailToggleBar}>
        <Button
          variant="default"
          onClick={() => setShowDetails((v) => !v)}
          disabled={details.length === 0}
        >
          {showDetails ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          {showDetails ? 'ЗГОРНУТИ ДЕТАЛЬНИЙ ЖУРНАЛ' : `ДЕТАЛЬНІШЕ ПРО ЗБИТТЯ (${details.length})`}
        </Button>

        {showDetails && (
          <div className={s.searchWrap}>
            <Search size={14} className={s.searchIco} />
            <input
              type="text"
              placeholder="Швидкий фільтр за бортом, типом чи сектором..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className={s.searchInput}
            />
          </div>
        )}
      </div>

      {/* ДЕТАЛЬНА ТАБЛИЦЯ У ФОРМАТІ БОЙОВОГО ЖУРНАЛУ */}
      {showDetails && (
        <div className={s.tableWrap}>
          <table className={s.table}>
            <thead>
              <tr>
                <th>№ Борта</th>
                <th>Джерело</th>
                <th>Тип БПЛА</th>
                <th>Час у симуляції</th>
                <th>Ціль ворога</th>
                <th>Комплекс РЕБ</th>
                <th>Точка падіння</th>
                <th>Зона падіння</th>
                <th>Уламки</th>
                <th>Служба 112</th>
                <th>Статус</th>
              </tr>
            </thead>
            <tbody>
              {filteredDetails.map((row) => (
                <tr key={row.id}>
                  <td><strong>{row.drone_id}</strong></td>
                  <td>
                    <Badge tone="info">🛰️ {row.data_source}</Badge>
                  </td>
                  <td><b>{row.drone_type}</b></td>
                  <td className={s.mono}>{row.downed_time}</td>
                  <td>{row.target_name}</td>
                  <td><span style={{ color: '#38bdf8', fontWeight: 600 }}>{row.interceptor_name}</span></td>
                  <td className={s.mono}>{row.crash_coords}</td>
                  <td>{row.crash_zone}</td>
                  <td className={s.mono}>~{row.debris_radius_m} м</td>
                  <td>
                    {row.emergency_112_called ? (
                      <span style={{ color: '#ef4444', display: 'inline-flex', alignItems: 'center', gap: 4, fontWeight: 700 }}>
                        <Siren size={13} /> ДСНС
                      </span>
                    ) : (
                      <span style={{ color: '#10b981' }}>Без загрози</span>
                    )}
                  </td>
                  <td>
                    <Badge tone={row.status === 'CRASHED' ? 'danger' : 'neutral'}>
                      {row.status === 'CRASHED' ? '💥 ЗБИТО' : '⚠️ ПРОРИВ'}
                    </Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};