// frontend/src/components/TacticalObjectModal.tsx
import React, { useState, useEffect } from 'react';
import { 
  Radio, Camera, Mic, Eye, Users, 
  Target, ShieldCheck, ShieldAlert, AlertTriangle, X, MapPin
} from 'lucide-react';
import { EWNode, TacticalSensor, TacticalZone, SensorType, ZoneType } from '../types';

export type EditableObject = 
  | { type: 'ew'; data: EWNode }
  | { type: 'sensor'; data: TacticalSensor }
  | { type: 'zone'; data: TacticalZone };

interface Props {
  initialLat: number;
  initialLon: number;
  initialCoordinates?: [number, number][];
  editingObject?: EditableObject | null;
  onClose: () => void;
  onSuccess: () => void;
}

type ObjectCategory = 
  | 'ew_node' 
  | 'camera' 
  | 'acoustic' 
  | 'observation_post' 
  | 'witness_report' 
  | 'target_asset'
  | 'danger_zone'
  | 'caution_zone'
  | 'safe_zone';

export const TacticalObjectModal: React.FC<Props> = ({ 
  initialLat, 
  initialLon, 
  initialCoordinates,
  editingObject, 
  onClose, 
  onSuccess 
}) => {
  const isEditing = !!editingObject;

  const [category, setCategory] = useState<ObjectCategory>(() => {
    if (initialCoordinates && initialCoordinates.length >= 3) {
      return 'safe_zone';
    }
    return 'ew_node';
  });

  const [name, setName] = useState('');
  const [lat, setLat] = useState(initialLat.toFixed(5));
  const [lon, setLon] = useState(initialLon.toFixed(5));
  const [radius, setRadius] = useState('2000');
  const [azimuth, setAzimuth] = useState('45');
  const [beamwidth, setBeamwidth] = useState('30');
  const [zoneRadius, setZoneRadius] = useState('1500');
  const [description, setDescription] = useState('');
  const [freeformCoordsText, setFreeformCoordsText] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (editingObject) {
      if (editingObject.type === 'ew') {
        const d = editingObject.data;
        setCategory('ew_node');
        setName(d.name);
        setLat(d.lat.toFixed(5));
        setLon(d.lon.toFixed(5));
        setRadius(d.max_range.toString());
        setAzimuth(d.azimuth.toString());
        setBeamwidth(d.beamwidth.toString());
      } else if (editingObject.type === 'sensor') {
        const d = editingObject.data;
        setCategory(d.sensor_type);
        setName(d.name);
        setLat(d.lat.toFixed(5));
        setLon(d.lon.toFixed(5));
        setRadius(d.detection_radius.toString());
        setDescription(d.description || '');
      } else if (editingObject.type === 'zone') {
        const d = editingObject.data;
        if (d.zone_type === 'safe') setCategory('safe_zone');
        else if (d.zone_type === 'caution') setCategory('caution_zone');
        else setCategory('danger_zone');
        setName(d.name);
        setFreeformCoordsText(d.coordinates.map(pt => `${pt[0].toFixed(5)}, ${pt[1].toFixed(5)}`).join('\n'));
      }
    } else {
      setLat(initialLat.toFixed(5));
      setLon(initialLon.toFixed(5));
      if (initialCoordinates && initialCoordinates.length >= 3) {
        setFreeformCoordsText(initialCoordinates.map(pt => `${pt[0].toFixed(5)}, ${pt[1].toFixed(5)}`).join('\n'));
      }
    }
  }, [editingObject, initialLat, initialLon, initialCoordinates]);

  const isZoneCategory = category === 'safe_zone' || category === 'caution_zone' || category === 'danger_zone';

  const parseCoordinates = (): [number, number][] => {
    if (freeformCoordsText.trim()) {
      const lines = freeformCoordsText.split('\n');
      const pts: [number, number][] = [];
      for (const line of lines) {
        const parts = line.split(/[,\s]+/).map(s => s.trim()).filter(Boolean);
        if (parts.length >= 2) {
          const plat = parseFloat(parts[0]);
          const plon = parseFloat(parts[1]);
          if (!isNaN(plat) && !isNaN(plon)) {
            pts.push([plat, plon]);
          }
        }
      }
      if (pts.length >= 3) {
        return pts;
      }
    }

    // Якщо список не заданий вручну — генеруємо коло навколо базової точки
    const fLat = parseFloat(lat);
    const fLon = parseFloat(lon);
    const radM = parseFloat(zoneRadius) || 1200;
    const mToLat = 1 / 111132.954;
    const mToLon = 1 / (111412.84 * Math.cos((fLat * Math.PI) / 180));
    const coords: [number, number][] = [];
    for (let i = 0; i < 8; i++) {
      const angle = (i * 45 * Math.PI) / 180;
      coords.push([
        round5(fLat + Math.cos(angle) * radM * mToLat),
        round5(fLon + Math.sin(angle) * radM * mToLon)
      ]);
    }
    return coords;
  };

  const round5 = (num: number) => Math.round(num * 100000) / 100000;

  const getTargetZoneType = (): ZoneType => {
    if (category === 'safe_zone') return 'safe';
    if (category === 'caution_zone') return 'caution';
    return 'danger';
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    const fLat = parseFloat(lat);
    const fLon = parseFloat(lon);
    const backendUrl = `http://${window.location.hostname}:8000`;

    try {
      if (isEditing && editingObject) {
        if (editingObject.type === 'ew') {
          await fetch(`${backendUrl}/api/v1/ew/node/${editingObject.data.id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              name,
              lat: fLat,
              lon: fLon,
              max_range: parseFloat(radius),
              beamwidth: parseFloat(beamwidth),
              current_azimuth: parseFloat(azimuth)
            })
          });
        } else if (editingObject.type === 'sensor') {
          await fetch(`${backendUrl}/api/v1/sensors/${editingObject.data.id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              name,
              sensor_type: category as SensorType,
              lat: fLat,
              lon: fLon,
              detection_radius: parseFloat(radius),
              description
            })
          });
        } else if (editingObject.type === 'zone') {
          const coords = parseCoordinates();
          await fetch(`${backendUrl}/api/v1/zones/${editingObject.data.id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              name,
              zone_type: getTargetZoneType(),
              coordinates: coords
            })
          });
        }
      } else {
        if (category === 'ew_node') {
          await fetch(`${backendUrl}/api/v1/ew/node`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              name: name || `РЕБ-${Math.floor(Math.random() * 900 + 100)}`,
              lat: fLat,
              lon: fLon,
              max_range: parseFloat(radius),
              beamwidth: parseFloat(beamwidth),
              current_azimuth: parseFloat(azimuth)
            })
          });
        } else if (isZoneCategory) {
          const coords = parseCoordinates();
          let defaultName = 'Тактична зона';
          if (category === 'safe_zone') defaultName = 'Зелена зона (Killbox)';
          else if (category === 'caution_zone') defaultName = 'Помаранчева зона (Буфер)';
          else defaultName = 'Червона зона (Заборона падіння)';

          await fetch(`${backendUrl}/api/v1/zones`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              name: name || defaultName,
              zone_type: getTargetZoneType(),
              coordinates: coords
            })
          });
        } else {
          await fetch(`${backendUrl}/api/v1/sensors`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              name: name || `${category.toUpperCase()}-${Math.floor(Math.random() * 900 + 100)}`,
              sensor_type: category,
              lat: fLat,
              lon: fLon,
              detection_radius: parseFloat(radius),
              description
            })
          });
        }
      }

      onSuccess();
      onClose();
    } catch (err) {
      console.error('Помилка збереження обʼєкта:', err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-overlay">
      <div className="tactical-modal">
        <div className="modal-header">
          <h3>{isEditing ? 'РЕДАГУВАННЯ ТАКТИЧНОГО ОБ\'ЄКТА' : 'СТВОРЕННЯ ТАКТИЧНОГО ОБ\'ЄКТА / ЗОНИ'}</h3>
          <button onClick={onClose} className="btn-close"><X size={18} /></button>
        </div>

        <form onSubmit={handleSubmit}>
          {!isEditing && (
            <div className="form-group">
              <label>Тип об'єкта або тактичної зони</label>
              <div className="category-grid">
                <button
                  type="button"
                  className={`cat-btn ${category === 'ew_node' ? 'active' : ''}`}
                  onClick={() => setCategory('ew_node')}
                >
                  <Radio size={15} color="#38bdf8" /> РЕБ (Спрямований)
                </button>
                <button
                  type="button"
                  className={`cat-btn ${category === 'target_asset' ? 'active' : ''}`}
                  onClick={() => setCategory('target_asset')}
                >
                  <Target size={15} color="#f87171" /> Критичний об'єкт
                </button>
                <button
                  type="button"
                  className={`cat-btn ${category === 'danger_zone' ? 'active danger' : ''}`}
                  onClick={() => setCategory('danger_zone')}
                >
                  <ShieldAlert size={15} color="#ef4444" /> Червона зона (No-drop)
                </button>
                <button
                  type="button"
                  className={`cat-btn ${category === 'caution_zone' ? 'active caution' : ''}`}
                  onClick={() => setCategory('caution_zone')}
                >
                  <AlertTriangle size={15} color="#f59e0b" /> Помаранчева зона (Буфер)
                </button>
                <button
                  type="button"
                  className={`cat-btn ${category === 'safe_zone' ? 'active safe' : ''}`}
                  onClick={() => setCategory('safe_zone')}
                >
                  <ShieldCheck size={15} color="#10b981" /> Зелена зона (Killbox)
                </button>
                <button
                  type="button"
                  className={`cat-btn ${category === 'camera' ? 'active' : ''}`}
                  onClick={() => setCategory('camera')}
                >
                  <Camera size={15} color="#34d399" /> Оптична камера
                </button>
                <button
                  type="button"
                  className={`cat-btn ${category === 'acoustic' ? 'active' : ''}`}
                  onClick={() => setCategory('acoustic')}
                >
                  <Mic size={15} color="#fbbf24" /> Акустичний пост
                </button>
                <button
                  type="button"
                  className={`cat-btn ${category === 'observation_post' ? 'active' : ''}`}
                  onClick={() => setCategory('observation_post')}
                >
                  <Eye size={15} color="#a78bfa" /> Мобільна вогнева група
                </button>
              </div>
            </div>
          )}

          <div className="form-group">
            <label>Позивний / Назва</label>
            <input
              type="text"
              placeholder={isZoneCategory ? "Наприклад: Район Вишгородських лісів" : "Наприклад: РЕБ-ГАРДА-2"}
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="tactical-input"
              required
            />
          </div>

          {/* КООРДИНАТИ ДЛЯ ЗОН ВІЛЬНОЇ ФОРМИ */}
          {isZoneCategory ? (
            <div className="form-group">
              <label style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span>Координати вершин вільної форми [Lat, Lon] (кожен рядок — точка)</span>
                <span style={{ color: '#38bdf8', fontSize: '0.7rem' }}>
                  {freeformCoordsText.split('\n').filter(l => l.trim()).length} вершин
                </span>
              </label>
              <textarea
                rows={5}
                className="tactical-input"
                style={{ fontFamily: 'monospace', fontSize: '0.75rem', lineHeight: '1.4' }}
                placeholder={`50.51234, 30.54321\n50.53456, 30.56789\n50.51987, 30.58912`}
                value={freeformCoordsText}
                onChange={(e) => setFreeformCoordsText(e.target.value)}
              />
              <div style={{ fontSize: '0.68rem', color: '#94a3b8', marginTop: '3px' }}>
                Порада: також можна скористатись кнопкою <b>«МАЛЮВАТИ ЗОНУ»</b> прямо на карті, щоб наклікати полігон.
              </div>
            </div>
          ) : (
            <div className="coords-row">
              <div className="form-group">
                <label>Широта (Lat)</label>
                <input
                  type="number"
                  step="any"
                  value={lat}
                  onChange={(e) => setLat(e.target.value)}
                  className="tactical-input"
                  required
                />
              </div>
              <div className="form-group">
                <label>Довгота (Lon)</label>
                <input
                  type="number"
                  step="any"
                  value={lon}
                  onChange={(e) => setLon(e.target.value)}
                  className="tactical-input"
                  required
                />
              </div>
            </div>
          )}

          {category === 'ew_node' && (
            <>
              <div className="coords-row">
                <div className="form-group">
                  <label>Азимут променя (°)</label>
                  <input
                    type="number"
                    min="0"
                    max="360"
                    value={azimuth}
                    onChange={(e) => setAzimuth(e.target.value)}
                    className="tactical-input"
                  />
                </div>
                <div className="form-group">
                  <label>Ширина променя (°)</label>
                  <input
                    type="number"
                    min="5"
                    max="120"
                    value={beamwidth}
                    onChange={(e) => setBeamwidth(e.target.value)}
                    className="tactical-input"
                  />
                </div>
              </div>
              <div className="form-group">
                <label>Радіус дії (м)</label>
                <input
                  type="number"
                  value={radius}
                  onChange={(e) => setRadius(e.target.value)}
                  className="tactical-input"
                />
              </div>
            </>
          )}

          {['camera', 'acoustic', 'observation_post', 'witness_report', 'target_asset'].includes(category) && (
            <>
              <div className="form-group">
                <label>Радіус виявлення / засікання (м)</label>
                <input
                  type="number"
                  value={radius}
                  onChange={(e) => setRadius(e.target.value)}
                  className="tactical-input"
                />
              </div>
              <div className="form-group">
                <label>Опис / Додаткові дані</label>
                <input
                  type="text"
                  placeholder="Оптичний канал, частоти або контакт"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  className="tactical-input"
                />
              </div>
            </>
          )}

          <div className="modal-actions">
            <button type="button" onClick={onClose} className="btn-secondary">СКАСУВАТИ</button>
            <button type="submit" disabled={loading} className="btn-primary">
              {loading ? 'ЗБЕРЕЖЕННЯ...' : isEditing ? 'ОНОВИТИ ДАНІ' : 'ЗБЕРЕГТИ ОБ\'ЄКТ В БД'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};