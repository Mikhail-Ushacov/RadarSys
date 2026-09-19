// frontend/src/components/TargetHUD.tsx
import React from 'react';
import { Track, EWNode, TacticalSensor, TacticalZone } from '../types';
import { 
  Crosshair, Zap, Plus, Camera, Mic, 
  Eye, Users, Target, ShieldAlert, ShieldCheck, Edit3, 
  MousePointerClick, Play, Square, RotateCcw, Grid, Compass, AlertOctagon
} from 'lucide-react';
import { EditableObject } from './TacticalObjectModal';

interface Props {
  tracks: Track[];
  ewNodes: EWNode[];
  sensors: TacticalSensor[];
  zones: TacticalZone[];
  allowMapClickToAdd: boolean;
  simulationActive: boolean;
  autoTracking: boolean;
  emergencyOverride: boolean;
  threatInfo: string | null;
  onToggleMapClickToAdd: () => void;
  onToggleSimulation: () => void;
  onToggleAutoTracking: () => void;
  onResetSimulation: () => void;
  onResetGrid: () => void;
  onTriggerBurst: (nodeId: number) => void;
  onOpenAddModal: () => void;
  onEditObject: (obj: EditableObject) => void;
}

export const TargetHUD: React.FC<Props> = ({ 
  tracks, ewNodes, sensors, zones,
  allowMapClickToAdd, simulationActive, autoTracking, emergencyOverride, threatInfo,
  onToggleMapClickToAdd, onToggleSimulation, onToggleAutoTracking, onResetSimulation, onResetGrid,
  onTriggerBurst, onOpenAddModal, onEditObject
}) => {
  return (
    <div className="sidebar">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #374151', paddingBottom: '0.6rem' }}>
        <h2 style={{ fontSize: '1.05rem', display: 'flex', alignItems: 'center', gap: '8px', margin: 0 }}>
          <Crosshair size={20} color="#38bdf8" /> SURGICAL C2 EW
        </h2>
        <button onClick={onOpenAddModal} className="btn-add-object">
          <Plus size={16} /> ДОДАТИ
        </button>
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
          <button onClick={onResetGrid} title="Скинути сітку зон" style={{ padding: '5px 8px', background: '#0369a1', border: 'none', color: '#fff', borderRadius: '4px', cursor: 'pointer' }}>
            <Grid size={14} />
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
          <span>Клік на карті (ЛКМ):</span>
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
        <div style={{ marginBottom: '1.2rem' }}>
          <h4 style={{ color: '#9ca3af', textTransform: 'uppercase', fontSize: '0.75rem', marginBottom: '0.4rem' }}>
            Активні цілі (Track Engine)
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
                  {t.status === 'CRASHED' ? '💥 DOWNED / CRASHED' :
                   t.status === 'JAMMED' ? '⚡ ПРИДУШЕНО (ПАДІННЯ)' :
                   t.is_ci_critical ? 'CI CRITICAL THREAT' :
                   (t.is_safe_to_engage ? 'KILLBOX CLEAR' : 'NO-STRIKE ZONE')}
                </span>
              </div>

              <div style={{ fontSize: '0.75rem', marginTop: '0.4rem', color: '#cbd5e1' }}>
                <div>Швидкість: <b style={{ color: '#38bdf8' }}>{(t.speed * 3.6).toFixed(0)} км/год</b> ({(t.speed).toFixed(1)} м/с)</div>
                <div>Висота: <b>{t.alt.toFixed(0)} м</b> | Курс: <b>{t.heading.toFixed(0)}°</b></div>
                {t.nearest_ci && (
                  <div style={{ marginTop: '3px', color: t.is_ci_critical ? '#fca5a5' : '#94a3b8' }}>
                    До {t.nearest_ci}: <b>{t.ci_distance} м</b>
                  </div>
                )}
                
                <div style={{ marginTop: '4px', fontWeight: 'bold' }}>
                  {t.status === 'CRASHED' ? (
                    <span style={{ color: '#ef4444' }}>💥 ЦІЛЬ ЗНЕШКОДЖЕНО РЕБ! Падіння на ґрунт. Очікування нової цілі...</span>
                  ) : t.status === 'JAMMED' ? (
                    <span style={{ color: '#f59e0b' }}>⚡ ВТРАТА GPS ТА КЕРУВАННЯ: Дрон зривається вниз під дією РЕБ</span>
                  ) : t.is_ci_critical ? (
                    <span style={{ color: '#ef4444' }}>⚠ ЗАГРОЗА ІНФРАСТРУКТУРІ: НЕГАЙНЕ ГЛУШІННЯ</span>
                  ) : t.is_safe_to_engage ? (
                    <span style={{ color: '#34d399' }}>✓ Зрив безпечний: падіння в зелену зону (Killbox)</span>
                  ) : (
                    <span style={{ color: '#f59e0b' }}>⏳ Очікування виходу в зелений коридор</span>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>

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

        <div style={{ marginBottom: '1.2rem' }}>
          <h4 style={{ color: '#9ca3af', textTransform: 'uppercase', fontSize: '0.75rem', marginBottom: '0.4rem' }}>
            Сенсори та об'єкти ({sensors.length})
          </h4>
          {sensors.map((s) => (
            <div key={s.id} style={{ background: '#111827', border: '1px solid #1f2937', padding: '0.5rem', borderRadius: '6px', marginBottom: '0.3rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
              {s.sensor_type === 'camera' && <Camera size={16} color="#34d399" />}
              {s.sensor_type === 'acoustic' && <Mic size={16} color="#fbbf24" />}
              {s.sensor_type === 'observation_post' && <Eye size={16} color="#a78bfa" />}
              {s.sensor_type === 'witness_report' && <Users size={16} color="#f472b6" />}
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

        <div>
          <h4 style={{ color: '#9ca3af', textTransform: 'uppercase', fontSize: '0.75rem', marginBottom: '0.4rem' }}>
            Тактичні зони ({zones.length})
          </h4>
          {zones.map((z) => (
            <div key={z.id} style={{ background: '#111827', border: '1px solid #1f2937', padding: '0.4rem 0.6rem', borderRadius: '6px', marginBottom: '0.3rem', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span style={{ fontSize: '0.75rem', display: 'flex', alignItems: 'center', gap: '6px' }}>
                {z.zone_type === 'safe' ? <ShieldCheck size={14} color="#10b981" /> : <ShieldAlert size={14} color="#ef4444" />}
                {z.name}
              </span>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <button onClick={() => onEditObject({ type: 'zone', data: z })} className="btn-icon-hud" title="Редагувати зону">
                  <Edit3 size={13} />
                </button>
                <span className={`badge ${z.zone_type === 'safe' ? 'badge-safe' : 'badge-danger'}`}>
                  {z.zone_type === 'safe' ? 'SAFE' : 'DANGER'}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};