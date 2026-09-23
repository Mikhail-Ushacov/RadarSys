// frontend/src/components/TargetHUD.tsx
import React from 'react';
import { Track, EWNode, TacticalSensor, TacticalZone, DownedDroneDetailed } from '../types';
import { 
  Crosshair, Zap, Plus, Camera, Mic, 
  Eye, Target, ShieldAlert, ShieldCheck, AlertTriangle, Edit3, 
  MousePointerClick, Play, Square, RotateCcw, Grid, Compass, AlertOctagon, History, ArrowRight, PenTool, Sparkles
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
}

export const TargetHUD: React.FC<Props> = ({ 
  tracks, ewNodes, sensors, zones, recentDowned, totalDownedCount,
  allowMapClickToAdd, isDrawingZone, simulationActive, autoTracking, emergencyOverride, threatInfo,
  onToggleMapClickToAdd, onStartDrawingZone, onGenerateFromH3, onToggleSimulation, onToggleAutoTracking, onResetSimulation, onResetGrid,
  onTriggerBurst, onOpenAddModal, onEditObject, onOpenHistoryPage
}) => {
  return (
    <div className="sidebar">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #374151', paddingBottom: '0.6rem' }}>
        <h2 style={{ fontSize: '1.05rem', display: 'flex', alignItems: 'center', gap: '8px', margin: 0 }}>
          <Crosshair size={20} color="#38bdf8" /> SURGICAL C2 EW
        </h2>
        <div style={{ display: 'flex', gap: '6px' }}>
          <button onClick={onOpenHistoryPage} className="btn-nav-history" title="Перейти до повного журналу збиттів">
            <History size={14} /> ЖУРНАЛ ({totalDownedCount})
          </button>
          <button onClick={onOpenAddModal} className="btn-add-object">
            <Plus size={15} /> ДОДАТИ
          </button>
        </div>
      </div>

      {threatInfo && (
        <div style={{
          marginTop: '0.6rem',
          background: emergencyOverride ? '#7f1d1d' : '#064e3b',
          border: `2px solid ${emergencyOverride ? '#ef4444' : '#10b981'}`,
          borderRadius: '6px', padding: '8px 10px',
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

      {/* ПАНЕЛЬ УПРАВЛІННЯ РЕЖИМАМИ ТА ГЕНЕРАЦІЄЮ ЗОН */}
      <div style={{ background: '#1e293b', border: '1px solid #334155', borderRadius: '6px', padding: '8px', marginTop: '0.6rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
          <span style={{ fontSize: '0.75rem', fontWeight: 'bold', color: '#94a3b8' }}>РЕЖИМ СУПРОВОДУ:</span>
          <button
            onClick={onToggleAutoTracking}
            style={{
              padding: '2px 6px', fontSize: '0.65rem', fontWeight: 'bold', borderRadius: '4px',
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
          <button onClick={onResetSimulation} title="Згенерувати новий випадковий спавн дрона" style={{ padding: '5px 8px', background: '#374151', border: 'none', color: '#fff', borderRadius: '4px', cursor: 'pointer' }}>
            <RotateCcw size={14} />
          </button>
          <button onClick={onResetGrid} title="Скинути сітку зон" style={{ padding: '5px 8px', background: '#475569', border: 'none', color: '#fff', borderRadius: '4px', cursor: 'pointer' }}>
            <Grid size={14} />
          </button>
        </div>

        {/* ШВИДКІ ІНСТРУМЕНТИ ЗОН: ГЕНЕРАЦІЯ З H3 ТА МАЛЮВАННЯ */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px', marginTop: '6px' }}>
          <button 
            onClick={onGenerateFromH3} 
            className="btn-zone-action"
            title="Перетворити гексагони з data/ у об'єднані полігональні райони"
          >
            <Sparkles size={12} color="#38bdf8" /> Згенерувати з H3
          </button>
          <button 
            onClick={onStartDrawingZone} 
            className={`btn-zone-action ${isDrawingZone ? 'active' : ''}`}
            title="Увімкнути режим малювання власної зони вільної форми кліком"
          >
            <PenTool size={12} color="#34d399" /> {isDrawingZone ? 'Малювання...' : 'Вільна форма'}
          </button>
        </div>
      </div>

      <div 
        className="click-mode-toggle-card"
        onClick={onToggleMapClickToAdd}
        style={{ cursor: 'pointer' }}
        title="Натисніть, щоб увімкнути/вимкнути створення об'єкта кліком по карті"
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

      <div style={{ flex: 1, overflowY: 'auto', marginTop: '0.6rem' }}>
        {/* АКТИВНІ ЦІЛІ В ПОВІТРІ */}
        <div style={{ marginBottom: '1.2rem' }}>
          <h4 style={{ color: '#9ca3af', textTransform: 'uppercase', fontSize: '0.75rem', marginBottom: '0.4rem', display: 'flex', justifyContent: 'space-between' }}>
            <span>Активні цілі в польоті</span>
            <span style={{ color: '#38bdf8' }}>{tracks.filter(t => t.status !== 'CRASHED').length}</span>
          </h4>
          {tracks.length === 0 && <p style={{ fontSize: '0.8rem', color: '#6b7280' }}>Очікування виявлення цілей...</p>}
          {tracks.map((t) => (
            <div 
              key={t.id} 
              style={{ 
                background: '#1f2937', 
                padding: '0.6rem', 
                borderRadius: '6px', 
                marginBottom: '0.4rem', 
                borderLeft: `4px solid ${
                  t.status === 'CRASHED' ? '#ef4444' :
                  t.status === 'JAMMED' ? '#f59e0b' :
                  t.is_ci_critical ? '#dc2626' : (t.is_safe_to_engage ? '#10b981' : '#f59e0b')
                }` 
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontWeight: 'bold', color: t.status === 'CRASHED' ? '#ef4444' : '#f87171' }}>{t.id}</span>
                <span className={`badge ${
                  t.status === 'CRASHED' ? 'badge-danger' :
                  t.status === 'JAMMED' ? 'badge-armed' :
                  t.is_ci_critical ? 'badge-jamming' :
                  (t.is_safe_to_engage ? 'badge-safe' : 'badge-danger')
                }`}>
                  {t.status === 'CRASHED' ? '💥 ЗБИТО' :
                   t.status === 'JAMMED' ? '⚡ ПРИДУШЕНО' :
                   t.is_ci_critical ? 'CI CRITICAL THREAT' :
                   (t.is_safe_to_engage ? 'KILLBOX CLEAR' : 'NO-STRIKE ZONE')}
                </span>
              </div>

              <div style={{ fontSize: '0.75rem', marginTop: '0.4rem', color: '#cbd5e1' }}>
                <div>Швидкість: <b style={{ color: '#38bdf8' }}>{(t.speed * 3.6).toFixed(0)} км/год</b></div>
                <div>Висота: <b>{t.alt.toFixed(0)} м</b> | Курс: <b>{t.heading.toFixed(0)}°</b></div>
                {t.target_asset_name && (
                  <div style={{ color: '#fbbf24', marginTop: '2px' }}>Ціль атаки: <b>{t.target_asset_name}</b></div>
                )}
                {t.nearest_ci && (
                  <div style={{ marginTop: '2px', color: t.is_ci_critical ? '#fca5a5' : '#94a3b8' }}>
                    До {t.nearest_ci}: <b>{t.ci_distance} м</b>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>

        {/* ВІДЖЕТ: ОСТАННІ 5 ЗБИТИХ ДРОНІВ */}
        <div style={{ marginBottom: '1.2rem', background: '#111827', border: '1px solid #1e293b', borderRadius: '6px', padding: '0.6rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
            <h4 style={{ color: '#9ca3af', textTransform: 'uppercase', fontSize: '0.75rem', margin: 0 }}>
              Останні 5 збитих цілей
            </h4>
            <span style={{ fontSize: '0.7rem', color: '#10b981', fontWeight: 'bold' }}>
              Всього: {totalDownedCount}
            </span>
          </div>

          {recentDowned.length === 0 ? (
            <p style={{ fontSize: '0.75rem', color: '#64748b', margin: '4px 0' }}>Ще не збито жодного дрона</p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              {recentDowned.map((d) => (
                <div key={d.id} className="mini-downed-item">
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <strong style={{ color: '#f87171', fontSize: '0.75rem' }}>{d.drone_id}</strong>
                    <span style={{ color: '#64748b', fontSize: '0.68rem' }}>{d.downed_time.split(' ')[1] || d.downed_time}</span>
                  </div>
                  <div style={{ fontSize: '0.7rem', color: '#94a3b8' }}>
                    Збито: <b style={{ color: '#a78bfa' }}>{d.interceptor_name}</b>
                  </div>
                  <div style={{ fontSize: '0.68rem', color: '#cbd5e1' }}>
                    Зона: {d.crash_zone}
                  </div>
                </div>
              ))}
            </div>
          )}

          <button onClick={onOpenHistoryPage} className="btn-view-all-history">
            Відкрити всю історію перехоплень ({totalDownedCount}) <ArrowRight size={13} />
          </button>
        </div>

        {/* ВУЗЛИ РЕБ */}
        <div style={{ marginBottom: '1.2rem' }}>
          <h4 style={{ color: '#9ca3af', textTransform: 'uppercase', fontSize: '0.75rem', marginBottom: '0.4rem' }}>
            Вузли РЕБ з автонаведенням ({ewNodes.length})
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

        {/* СЕНСОРИ */}
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

        {/* ТАКТИЧНІ ЗОНИ (3 ТИПИ: SAFE, CAUTION, DANGER) */}
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