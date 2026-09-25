// frontend/src/components/TargetHUD.tsx
import React, { useState } from 'react';
import { Track, EWNode, TacticalSensor, TacticalZone, DownedDroneDetailed } from '../types';
import { 
  Crosshair, Zap, Plus, Camera, Mic, 
  Eye, Target, ShieldAlert, ShieldCheck, AlertTriangle, Edit3, 
  MousePointerClick, Play, Square, RotateCcw, Grid, Compass, 
  AlertOctagon, History, ArrowRight, PenTool, Sparkles, Database, Users 
} from 'lucide-react';
import { EditableObject } from './TacticalObjectModal';

interface Props {
  tracks: Track[];
  ewNodes: EWNode[];
  sensors: TacticalSensor[];
  zones: TacticalZone[];
  recentDowned: DownedDroneDetailed[];
  totalDownedCount: number;
  allowMapClickToAdd: boolean;
  isDrawingZone: boolean;
  simulationActive: boolean;
  autoTracking: boolean;
  emergencyOverride: boolean;
  threatInfo: string | null;
  onToggleMapClickToAdd: () => void;
  onStartDrawingZone: () => void;
  onGenerateFromH3: () => void;
  onToggleSimulation: () => void;
  onToggleAutoTracking: () => void;
  onResetSimulation: () => void;
  onResetGrid: () => void;
  onTriggerBurst: (nodeId: number) => void;
  onOpenAddModal: () => void;
  onEditObject: (obj: EditableObject) => void;
  onOpenHistoryPage: () => void;
  onSeedData?: () => void;
  onOptimizeEW?: () => Promise<void> | void;
}

export const TargetHUD: React.FC<Props> = ({ 
  tracks, ewNodes, sensors, zones, recentDowned, totalDownedCount,
  allowMapClickToAdd, isDrawingZone, simulationActive, autoTracking, emergencyOverride, threatInfo,
  onToggleMapClickToAdd, onStartDrawingZone, onGenerateFromH3, onToggleSimulation, onToggleAutoTracking, 
  onResetSimulation, onResetGrid, onTriggerBurst, onOpenAddModal, onEditObject, onOpenHistoryPage, onSeedData,
  onOptimizeEW
}) => {
  const [seeding, setSeeding] = useState(false);

  const handleSeed = async () => {
    if (onSeedData) {
      onSeedData();
      return;
    }
    try {
      setSeeding(true);
      const res = await fetch(`http://${window.location.hostname}:8000/api/v1/seed`, { method: 'POST' });
      if (res.ok) {
        alert('Базу даних успішно наповнено новими тактичними сенсорами, камерами, РЕБ та зонами!');
      }
    } catch (e) {
      console.error('Помилка виконання seed:', e);
    } finally {
      setSeeding(false);
    }
  };

  const [isOptimizing, setIsOptimizing] = useState(false);

  const handleRunOptimization = async () => {
    if (!confirm('Перерахувати оптимальні позиції комплексів РЕБ за даними H3 та ОКІ?')) return;
    try {
      setIsOptimizing(true);
      if (onOptimizeEW) {
        await onOptimizeEW();
      } else {
        const res = await fetch(`http://${window.location.hostname}:8000/api/v1/ew/optimize?node_count=5&replace=true`, { method: 'POST' });
        const data = await res.json();
        if (data.status === 'success') {
          alert(`Успішно оптимізовано ${data.count} комплексів РЕБ!`);
        }
      }
    } catch (e) {
      console.error(e);
      alert('Помилка оптимізації РЕБ');
    } finally {
      setIsOptimizing(false);
    }
  };

  return (
    <div className="sidebar">
      {/* Верхня панель HUD */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #374151', paddingBottom: '0.6rem' }}>
        <h2 style={{ fontSize: '1.05rem', display: 'flex', alignItems: 'center', gap: '8px', margin: 0, color: '#f8fafc' }}>
          <Crosshair size={20} color="#38bdf8" /> SURGICAL C2 EW
        </h2>
        <div style={{ display: 'flex', gap: '6px' }}>
          <button onClick={onOpenHistoryPage} className="btn-nav-history" title="Перейти до повного журналу збиттів">
            <History size={14} /> ЖУРНАЛ ({totalDownedCount})
          </button>
          <button onClick={onOpenAddModal} className="btn-add-object" title="Додати новий об'єкт або зону вручну">
            <Plus size={15} /> ДОДАТИ
          </button>
        </div>
        <div style={{ display: 'flex', gap: '6px' }}>
          <button 
            onClick={handleRunOptimization}
            disabled={isOptimizing}
            className="btn-zone-action"
            title="Автоматичний розрахунок оптимальних рубежів РЕБ"
            style={{ opacity: isOptimizing ? 0.6 : 1, cursor: isOptimizing ? 'wait' : 'pointer' }}
          >
            <Compass size={12} color="#38bdf8" /> {isOptimizing ? 'Розрахунок...' : 'Оптимізувати РЕБ'}
          </button>
        </div>
      </div>

      {/* Сповіщення про тактичну загрозу або перехоплення */}
      {threatInfo && (
        <div style={{
          marginTop: '0.6rem',
          background: emergencyOverride ? '#7f1d1d' : '#064e3b',
          border: `2px solid ${emergencyOverride ? '#ef4444' : '#10b981'}`,
          borderRadius: '6px',
          padding: '8px 10px',
          animation: emergencyOverride ? 'blink 1s infinite' : 'none'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#fff', fontWeight: 'bold', fontSize: '0.8rem' }}>
            <AlertOctagon size={16} color={emergencyOverride ? '#fca5a5' : '#a7f3d0'} /> ТАКТИЧНА ДІЯ:
          </div>
          <div style={{ fontSize: '0.72rem', color: '#f1f5f9', marginTop: '3px' }}>
            {threatInfo}
          </div>
        </div>
      )}

      {/* Панель управління режимами та моделюванням */}
      <div style={{ background: '#1e293b', border: '1px solid #334155', borderRadius: '6px', padding: '8px', marginTop: '0.6rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
          <span style={{ fontSize: '0.75rem', fontWeight: 'bold', color: '#94a3b8' }}>РЕЖИМ СУПРОВОДУ:</span>
          <button
            onClick={onToggleAutoTracking}
            style={{
              padding: '2px 8px', fontSize: '0.65rem', fontWeight: 'bold', borderRadius: '4px',
              border: 'none', cursor: 'pointer', background: autoTracking ? '#0284c7' : '#475569', color: '#fff',
              display: 'flex', alignItems: 'center', gap: '4px'
            }}
          >
            <Compass size={11} /> {autoTracking ? 'LEAD-ANGLE ON' : 'MANUAL'}
          </button>
        </div>

        <div style={{ display: 'flex', gap: '6px' }}>
          <button 
            onClick={onToggleSimulation}
            style={{
              flex: 1, padding: '5px', fontSize: '0.75rem', fontWeight: 'bold', borderRadius: '4px',
              border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '4px',
              background: simulationActive ? '#f59e0b' : '#10b981', color: 'white'
            }}
          >
            {simulationActive ? <><Square size={13} /> ПАУЗА</> : <><Play size={13} /> СТАРТ</>}
          </button>
          <button 
            onClick={onResetSimulation} 
            title="Перезапустити випадкову появу дрона за містом" 
            style={{ padding: '5px 8px', background: '#374151', border: 'none', color: '#fff', borderRadius: '4px', cursor: 'pointer' }}
          >
            <RotateCcw size={14} />
          </button>
          <button 
            onClick={handleSeed} 
            disabled={seeding}
            title="Завантажити новий логічний Seed (камери, мікрофони, МВГ, РЕБ)" 
            style={{ padding: '5px 8px', background: '#0284c7', border: 'none', color: '#fff', borderRadius: '4px', cursor: 'pointer' }}
          >
            <Database size={14} />
          </button>
          <button 
            onClick={onResetGrid} 
            title="Очистити всі зони, сенсори та вузли РЕБ" 
            style={{ padding: '5px 8px', background: '#475569', border: 'none', color: '#fff', borderRadius: '4px', cursor: 'pointer' }}
          >
            <Grid size={14} />
          </button>
        </div>

        {/* Швидкі дії із зонами */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px', marginTop: '6px' }}>
          <button 
            onClick={onGenerateFromH3} 
            className="btn-zone-action"
            title="Об'єднати H3 гексагони у суцільні райони безпеки"
          >
            <Sparkles size={12} color="#38bdf8" /> Згенерувати з H3
          </button>
          <button 
            onClick={onStartDrawingZone} 
            className={`btn-zone-action ${isDrawingZone ? 'active' : ''}`}
            title="Малювати зону довільної форми кліками на карті"
          >
            <PenTool size={12} color="#34d399" /> {isDrawingZone ? 'Малювання...' : 'Вільна форма'}
          </button>
        </div>
      </div>

      {/* Перемикач режиму кліку на карті */}
      <div 
        className="click-mode-toggle-card"
        onClick={onToggleMapClickToAdd}
        style={{ cursor: 'pointer' }}
        title="Натисніть, щоб увімкнути або вимкнути додавання об'єкта кліком по карті"
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.75rem', color: '#94a3b8' }}>
          <MousePointerClick size={15} color={allowMapClickToAdd ? '#38bdf8' : '#64748b'} />
          <span>Клік на карті (додати точку):</span>
        </div>
        <button 
          type="button"
          onClick={(e) => { e.stopPropagation(); onToggleMapClickToAdd(); }}
          className={`btn-toggle-switch ${allowMapClickToAdd ? 'enabled' : 'disabled'}`}
        >
          {allowMapClickToAdd ? 'УВІМКНЕНО' : 'ВИМКНЕНО'}
        </button>
      </div>

      {/* Основний список із прокруткою */}
      <div style={{ flex: 1, overflowY: 'auto', marginTop: '0.6rem' }}>
        
        {/* РОЗДІЛ: АКТИВНІ ЦІЛІ В ПОВІТРІ */}
        <div style={{ marginBottom: '1.2rem' }}>
          <h4 style={{ color: '#9ca3af', textTransform: 'uppercase', fontSize: '0.75rem', marginBottom: '0.4rem', display: 'flex', justifyContent: 'space-between' }}>
            <span>Повітряна обстановка (БПЛА)</span>
            <span style={{ color: '#38bdf8' }}>{tracks.filter(t => t.status !== 'CRASHED').length}</span>
          </h4>

          {tracks.length === 0 ? (
            <div style={{ padding: '0.8rem', background: '#111827', borderRadius: '6px', border: '1px dashed #334155', textAlign: 'center', fontSize: '0.75rem', color: '#64748b' }}>
              Цілей у зоні виявлення немає.<br />
              <span style={{ fontSize: '0.68rem', color: '#475569' }}>
                Дрон летить за містом, очікується фіксація сенсорами або камерами...
              </span>
            </div>
          ) : (
            tracks.map((t) => {
              const isInitial = t.detection_stage === 'INITIAL_CONTACT' || t.status === 'DETECTING';
              return (
                <div 
                  key={t.id} 
                  style={{ 
                    background: '#1f2937', 
                    padding: '0.6rem', 
                    borderRadius: '6px', 
                    marginBottom: '0.5rem', 
                    borderLeft: `4px solid ${
                      t.status === 'CRASHED' ? '#ef4444' :
                      t.status === 'JAMMED' ? '#f59e0b' :
                      isInitial ? '#f59e0b' :
                      t.is_ci_critical ? '#dc2626' : (t.is_safe_to_engage ? '#10b981' : '#ef4444')
                    }` 
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontWeight: 'bold', color: t.status === 'CRASHED' ? '#ef4444' : '#f87171', fontSize: '0.85rem' }}>
                      {t.id}
                    </span>
                    <span className={`badge ${
                      t.status === 'CRASHED' ? 'badge-danger' :
                      t.status === 'JAMMED' ? 'badge-armed' :
                      isInitial ? 'badge-caution' :
                      t.is_ci_critical ? 'badge-jamming' :
                      (t.is_safe_to_engage ? 'badge-safe' : 'badge-danger')
                    }`}>
                      {t.status === 'CRASHED' ? '💥 ЗБИТО' :
                       t.status === 'JAMMED' ? '⚡ ПРИДУШЕНО' :
                       isInitial ? '⚠️ 1-Й КОНТАКТ' :
                       t.is_ci_critical ? 'CI CRITICAL THREAT' :
                       (t.is_safe_to_engage ? 'KILLBOX CLEAR' : 'NO-STRIKE ZONE')}
                    </span>
                  </div>

                  <div style={{ fontSize: '0.75rem', marginTop: '0.4rem', color: '#cbd5e1' }}>
                    {isInitial ? (
                      /* СТАДІЯ 1: Первинний контакт */
                      <div style={{ background: '#451a03', padding: '6px', borderRadius: '4px', border: '1px dashed #f59e0b', color: '#fde047' }}>
                        <div style={{ fontWeight: 'bold', display: 'flex', alignItems: 'center', gap: '4px' }}>
                          <AlertTriangle size={13} color="#f59e0b" /> Засічка: {t.last_sensor}
                        </div>
                        <div style={{ fontSize: '0.68rem', marginTop: '3px', color: '#fed7aa', lineHeight: '1.3' }}>
                          Вектор швидкості, курс та ціль <b>НЕВІДОМІ</b>. Очікується 2-й контакт (камера, мікрофон, МВГ або 112) для визначення кінематики.
                        </div>
                      </div>
                    ) : (
                      /* СТАДІЯ 2: Супровід із визначеним вектором */
                      <div style={{ background: '#0f172a', padding: '6px', borderRadius: '4px', border: '1px solid #1e293b' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', color: '#38bdf8', marginBottom: '2px' }}>
                          <span>Швидкість: <b>{t.speed !== null ? `${(t.speed * 3.6).toFixed(0)} км/год` : '?'}</b></span>
                          <span>Курс: <b>{t.heading !== null ? `${t.heading.toFixed(0)}°` : '?'}</b></span>
                        </div>
                        <div>Висота: <b>{t.alt.toFixed(0)} м</b> | Засічок: <b>{t.detection_count || 2}</b></div>
                        
                        {t.kinematics_note && (
                          <div style={{ fontSize: '0.68rem', color: '#34d399', marginTop: '3px', fontFamily: 'monospace' }}>
                            📐 {t.kinematics_note}
                          </div>
                        )}

                        {t.target_asset_name && (
                          <div style={{ color: '#fbbf24', marginTop: '3px', fontSize: '0.72rem', fontWeight: '500' }}>
                            🎯 Ймовірна ціль: <b>{t.target_asset_name}</b>
                          </div>
                        )}

                        {t.nearest_ci && (
                          <div style={{ marginTop: '2px', color: t.is_ci_critical ? '#fca5a5' : '#94a3b8', fontSize: '0.7rem' }}>
                            До {t.nearest_ci}: <b>{t.ci_distance} м</b>
                          </div>
                        )}

                        {t.crash_safety !== null && t.crash_safety !== undefined && (
                          <div style={{ marginTop: '2px', fontSize: '0.7rem' }}>
                            Безпека падіння: <b style={{ color: t.crash_safety >= 60 ? '#34d399' : t.crash_safety >= 40 ? '#fbbf24' : '#f87171' }}>
                              {t.crash_safety.toFixed(1)}%
                            </b>
                          </div>
                        )}

                        {/* Хронологія сенсорних засічок */}
                        {t.detection_timeline && t.detection_timeline.length > 0 && (
                          <div style={{ marginTop: '5px', borderTop: '1px dashed #334155', paddingTop: '4px' }}>
                            <div style={{ fontSize: '0.65rem', color: '#94a3b8', textTransform: 'uppercase' }}>Ланцюжок виявлення:</div>
                            {t.detection_timeline.map((line, idx) => (
                              <div key={idx} style={{ fontSize: '0.65rem', color: '#cbd5e1' }}>• {line}</div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* ВІДЖЕТ: ОСТАННІ 5 ЗБИТИХ ДРОНІВ */}
        <div style={{ marginBottom: '1.2rem', background: '#111827', border: '1px solid #1e293b', borderRadius: '6px', padding: '0.6rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
            <h4 style={{ color: '#9ca3af', textTransform: 'uppercase', fontSize: '0.75rem', margin: 0 }}>
              Останні збиті цілі
            </h4>
            <span style={{ fontSize: '0.7rem', color: '#10b981', fontWeight: 'bold' }}>
              Всього: {totalDownedCount}
            </span>
          </div>

          {recentDowned.length === 0 ? (
            <p style={{ fontSize: '0.75rem', color: '#64748b', margin: '4px 0' }}>Журнал порожній (цілі ще не утилізовано)</p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              {recentDowned.map((d) => (
                <div key={d.id} className="mini-downed-item">
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <strong style={{ color: '#f87171', fontSize: '0.75rem' }}>{d.drone_id}</strong>
                    <span style={{ color: '#64748b', fontSize: '0.68rem' }}>{d.downed_time.split(' ')[1] || d.downed_time}</span>
                  </div>
                  <div style={{ fontSize: '0.7rem', color: '#94a3b8' }}>
                    Комплекс: <b style={{ color: '#a78bfa' }}>{d.interceptor_name}</b>
                  </div>
                  <div style={{ fontSize: '0.68rem', color: '#cbd5e1' }}>
                    Зона: {d.crash_zone}
                  </div>
                </div>
              ))}
            </div>
          )}

          <button onClick={onOpenHistoryPage} className="btn-view-all-history">
            Повний журнал збиттів ({totalDownedCount}) <ArrowRight size={13} />
          </button>
        </div>

        {/* РОЗДІЛ: ВУЗЛИ РЕБ */}
        <div style={{ marginBottom: '1.2rem' }}>
          <h4 style={{ color: '#9ca3af', textTransform: 'uppercase', fontSize: '0.75rem', marginBottom: '0.4rem' }}>
            Комплекси РЕБ ({ewNodes.length})
          </h4>
          {ewNodes.map((n) => (
            <div key={n.id} style={{ background: '#1f2937', padding: '0.6rem', borderRadius: '6px', marginBottom: '0.5rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontWeight: 'bold', fontSize: '0.85rem' }}>{n.name}</span>
                <div style={{ display: 'flex', gap: '4px', alignItems: 'center' }}>
                  <button onClick={() => onEditObject({ type: 'ew', data: n })} className="btn-icon-hud" title="Редагувати параметри РЕБ">
                    <Edit3 size={13} />
                  </button>
                  <span className={`badge ${n.is_transmitting ? 'badge-jamming' : n.is_armed ? 'badge-armed' : ''}`}>
                    {n.is_transmitting ? 'BURST ACTIVE' : n.is_armed ? 'TRACKING' : 'STANDBY'}
                  </span>
                </div>
              </div>
              <div style={{ fontSize: '0.75rem', margin: '0.3rem 0', color: '#cbd5e1' }}>
                Кут: <b style={{ color: '#38bdf8' }}>{n.azimuth}°</b> | Промінь: <b style={{ color: '#34d399' }}>{n.beamwidth}°</b> | R: <b>{n.max_range}м</b>
              </div>
              <button
                onClick={() => onTriggerBurst(n.id)}
                disabled={n.is_transmitting}
                style={{
                  width: '100%', padding: '0.4rem',
                  background: n.is_transmitting ? '#dc2626' : '#0284c7',
                  border: 'none', color: 'white', borderRadius: '4px',
                  cursor: n.is_transmitting ? 'not-allowed' : 'pointer',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px',
                  fontWeight: 'bold', fontSize: '0.8rem'
                }}
              >
                <Zap size={14} /> {n.is_transmitting ? 'АКТИВНЕ ПРИДУШЕННЯ...' : '20s ПРИМУСОВИЙ BURST'}
              </button>
            </div>
          ))}
        </div>

        {/* РОЗДІЛ: СЕНСОРИ ТА КРИТИЧНІ ОБ'ЄКТИ */}
        <div style={{ marginBottom: '1.2rem' }}>
          <h4 style={{ color: '#9ca3af', textTransform: 'uppercase', fontSize: '0.75rem', marginBottom: '0.4rem' }}>
            Сенсори та об'єкти ({sensors.length})
          </h4>
          {sensors.map((s) => (
            <div key={s.id} style={{ background: '#111827', border: '1px solid #1f2937', padding: '0.5rem', borderRadius: '6px', marginBottom: '0.3rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
              {s.sensor_type === 'camera' && <Camera size={16} color="#34d399" />}
              {s.sensor_type === 'acoustic' && <Mic size={16} color="#fbbf24" />}
              {s.sensor_type === 'observation_post' && <Eye size={16} color="#a78bfa" />}
              {s.sensor_type === 'target_asset' && <Target size={16} color="#f87171" />}
              {s.sensor_type === 'witness_report' && <Users size={16} color="#f472b6" />}
              <div style={{ fontSize: '0.75rem', flex: 1 }}>
                <div style={{ fontWeight: 'bold', color: s.sensor_type === 'target_asset' ? '#fca5a5' : '#e2e8f0' }}>{s.name}</div>
                <div style={{ color: '#9ca3af' }}>R: {s.detection_radius}м {s.description ? `• ${s.description}` : ''}</div>
              </div>
              <button onClick={() => onEditObject({ type: 'sensor', data: s })} className="btn-icon-hud" title="Редагувати">
                <Edit3 size={13} />
              </button>
            </div>
          ))}
        </div>

        {/* РОЗДІЛ: ТАКТИЧНІ РАЙОНИ */}
        <div>
          <h4 style={{ color: '#9ca3af', textTransform: 'uppercase', fontSize: '0.75rem', marginBottom: '0.4rem' }}>
            Тактичні райони ({zones.length})
          </h4>
          {zones.map((z) => (
            <div key={z.id} style={{ background: '#111827', border: '1px solid #1f2937', padding: '0.4rem 0.6rem', borderRadius: '6px', marginBottom: '0.3rem', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span style={{ fontSize: '0.75rem', display: 'flex', alignItems: 'center', gap: '6px' }}>
                {z.zone_type === 'safe' && <ShieldCheck size={14} color="#10b981" />}
                {z.zone_type === 'caution' && <AlertTriangle size={14} color="#f59e0b" />}
                {z.zone_type === 'danger' && <ShieldAlert size={14} color="#ef4444" />}
                {z.name}
              </span>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <button onClick={() => onEditObject({ type: 'zone', data: z })} className="btn-icon-hud" title="Редагувати зону">
                  <Edit3 size={13} />
                </button>
                <span className={`badge ${
                  z.zone_type === 'safe' ? 'badge-safe' :
                  z.zone_type === 'caution' ? 'badge-caution' : 'badge-danger'
                }`}>
                  {z.zone_type === 'safe' ? 'KILLBOX' : z.zone_type === 'caution' ? 'CAUTION' : 'NO-DROP'}
                </span>
              </div>
            </div>
          ))}
        </div>

      </div>
    </div>
  );
};