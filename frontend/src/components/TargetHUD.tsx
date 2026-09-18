// frontend/src/components/TargetHUD.tsx
import React from 'react';
import { Track, EWNode, TacticalSensor, TacticalZone } from '../types';
import { 
  Crosshair, Zap, Plus, Camera, Mic, 
  Eye, Users, Target, ShieldAlert, ShieldCheck, Edit3, MousePointerClick
} from 'lucide-react';
import { EditableObject } from './TacticalObjectModal';

interface Props {
  tracks: Track[];
  ewNodes: EWNode[];
  sensors: TacticalSensor[];
  zones: TacticalZone[];
  allowMapClickToAdd: boolean;
  onToggleMapClickToAdd: () => void;
  onTriggerBurst: (nodeId: number) => void;
  onOpenAddModal: () => void;
  onEditObject: (obj: EditableObject) => void;
}

export const TargetHUD: React.FC<Props> = ({ 
  tracks, ewNodes, sensors, zones,
  allowMapClickToAdd, onToggleMapClickToAdd,
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

      {/* Перемикач кліку додавання по карті */}
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
          onClick={(e) => {
            e.stopPropagation();
            onToggleMapClickToAdd();
          }}
          className={`btn-toggle-switch ${allowMapClickToAdd ? 'enabled' : 'disabled'}`}
        >
          {allowMapClickToAdd ? 'УВІМКНЕНО' : 'ВИМКНЕНО'}
        </button>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', marginTop: '0.6rem' }}>
        {/* Активні загрози */}
        <div style={{ marginBottom: '1.2rem' }}>
          <h4 style={{ color: '#9ca3af', textTransform: 'uppercase', fontSize: '0.75rem', marginBottom: '0.4rem' }}>
            Активні цілі (Track Engine)
          </h4>
          {tracks.length === 0 && <p style={{ fontSize: '0.8rem', color: '#6b7280' }}>Немає активних загроз</p>}
          {tracks.map((t) => (
            <div key={t.id} style={{ background: '#1f2937', padding: '0.6rem', borderRadius: '6px', marginBottom: '0.4rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontWeight: 'bold', color: '#ef4444' }}>{t.id}</span>
                <span className={`badge ${t.is_safe_to_engage ? 'badge-safe' : 'badge-danger'}`}>
                  {t.is_safe_to_engage ? 'KILLBOX CLEAR' : 'NO-STRIKE ZONE'}
                </span>
              </div>
              <div style={{ fontSize: '0.75rem', marginTop: '0.3rem', color: '#cbd5e1' }}>
                <div>Швидкість: <b>{(t.speed * 3.6).toFixed(0)} км/год</b></div>
                <div>Висота: <b>{t.alt.toFixed(0)} м</b> | Курс: <b>{t.heading.toFixed(0)}°</b></div>
              </div>
            </div>
          ))}
        </div>

        {/* Вузли РЕБ */}
        <div style={{ marginBottom: '1.2rem' }}>
          <h4 style={{ color: '#9ca3af', textTransform: 'uppercase', fontSize: '0.75rem', marginBottom: '0.4rem' }}>
            Вузли РЕБ ({ewNodes.length})
          </h4>
          {ewNodes.map((n) => (
            <div key={n.id} style={{ background: '#1f2937', padding: '0.6rem', borderRadius: '6px', marginBottom: '0.5rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontWeight: 'bold', fontSize: '0.85rem' }}>{n.name}</span>
                <div style={{ display: 'flex', gap: '4px', alignItems: 'center' }}>
                  <button 
                    onClick={() => onEditObject({ type: 'ew', data: n })}
                    className="btn-icon-hud"
                    title="Редагувати параметри РЕБ"
                  >
                    <Edit3 size={13} />
                  </button>
                  <span className={`badge ${n.is_transmitting ? 'badge-jamming' : n.is_armed ? 'badge-armed' : ''}`}>
                    {n.is_transmitting ? 'BURST' : n.is_armed ? 'ARMED' : 'STANDBY'}
                  </span>
                </div>
              </div>
              <div style={{ fontSize: '0.75rem', margin: '0.3rem 0', color: '#cbd5e1' }}>
                Азимут: <b>{n.azimuth}°</b> (Кут {n.beamwidth}°) | R: <b>{n.max_range}м</b>
              </div>
              <button
                onClick={() => onTriggerBurst(n.id)}
                disabled={n.is_transmitting}
                style={{
                  width: '100%',
                  padding: '0.4rem',
                  background: n.is_transmitting ? '#6b7280' : '#dc2626',
                  border: 'none',
                  color: 'white',
                  borderRadius: '4px',
                  cursor: n.is_transmitting ? 'not-allowed' : 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '6px',
                  fontWeight: 'bold',
                  fontSize: '0.8rem'
                }}
              >
                <Zap size={14} /> 20s SURGICAL BURST
              </button>
            </div>
          ))}
        </div>

        {/* Сенсори */}
        <div style={{ marginBottom: '1.2rem' }}>
          <h4 style={{ color: '#9ca3af', textTransform: 'uppercase', fontSize: '0.75rem', marginBottom: '0.4rem' }}>
            Сенсори та спостереження ({sensors.length})
          </h4>
          {sensors.map((s) => (
            <div key={s.id} style={{ background: '#111827', border: '1px solid #1f2937', padding: '0.5rem', borderRadius: '6px', marginBottom: '0.3rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
              {s.sensor_type === 'camera' && <Camera size={16} color="#34d399" />}
              {s.sensor_type === 'acoustic' && <Mic size={16} color="#fbbf24" />}
              {s.sensor_type === 'observation_post' && <Eye size={16} color="#a78bfa" />}
              {s.sensor_type === 'witness_report' && <Users size={16} color="#f472b6" />}
              {s.sensor_type === 'target_asset' && <Target size={16} color="#f87171" />}
              <div style={{ fontSize: '0.75rem', flex: 1 }}>
                <div style={{ fontWeight: 'bold' }}>{s.name}</div>
                <div style={{ color: '#9ca3af' }}>R: {s.detection_radius}м {s.description ? `• ${s.description}` : ''}</div>
              </div>
              <button 
                onClick={() => onEditObject({ type: 'sensor', data: s })}
                className="btn-icon-hud"
                title="Редагувати сенсор"
              >
                <Edit3 size={13} />
              </button>
            </div>
          ))}
        </div>

        {/* Тактичні зони */}
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
                <button 
                  onClick={() => onEditObject({ type: 'zone', data: z })}
                  className="btn-icon-hud"
                  title="Редагувати зону"
                >
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