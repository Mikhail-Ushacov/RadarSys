// frontend/src/components/TacticalObjectModal.tsx
import React, { useState, useEffect } from 'react';
import { 
  Radio, Camera, Mic, Eye, Users, 
  Target, ShieldCheck, ShieldAlert, X 
} from 'lucide-react';
import { EWNode, TacticalSensor, TacticalZone, SensorType } from '../types';

export type EditableObject = 
  | { type: 'ew'; data: EWNode }
  | { type: 'sensor'; data: TacticalSensor }
  | { type: 'zone'; data: TacticalZone };

interface Props {
  initialLat: number;
  initialLon: number;
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
  | 'safe_zone';

export const TacticalObjectModal: React.FC<Props> = ({ 
  initialLat, 
  initialLon, 
  editingObject, 
  onClose, 
  onSuccess 
}) => {
  const isEditing = !!editingObject;

  const [category, setCategory] = useState<ObjectCategory>('ew_node');
  const [name, setName] = useState('');
  const [lat, setLat] = useState(initialLat.toFixed(5));
  const [lon, setLon] = useState(initialLon.toFixed(5));
  const [radius, setRadius] = useState('2000');
  const [azimuth, setAzimuth] = useState('45');
  const [beamwidth, setBeamwidth] = useState('30');
  const [zoneRadius, setZoneRadius] = useState('1500');
  const [description, setDescription] = useState('');
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
        setCategory(d.zone_type === 'safe' ? 'safe_zone' : 'danger_zone');
        setName(d.name);
      }
    } else {
      setLat(initialLat.toFixed(5));
      setLon(initialLon.toFixed(5));
    }
  }, [editingObject, initialLat, initialLon]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    const fLat = parseFloat(lat);
    const fLon = parseFloat(lon);
    const backendUrl = `http://${window.location.hostname}:8000`;

    try {
      if (isEditing && editingObject) {
        // --- РЕДАГУВАННЯ ІСНУЮЧОГО ОБ'ЄКТА ---
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
          await fetch(`${backendUrl}/api/v1/zones/${editingObject.data.id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              name,
              zone_type: category === 'safe_zone' ? 'safe' : 'danger'
            })
          });
        }
      } else {
        // --- СТВОРЕННЯ НОВОГО ОБ'ЄКТА ---
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
        } else if (category === 'safe_zone' || category === 'danger_zone') {
          const radM = parseFloat(zoneRadius);
          const mToLat = 1 / 111132.954;
          const mToLon = 1 / (111412.84 * Math.cos((fLat * Math.PI) / 180));
          const coords: [number, number][] = [];
          for (let i = 0; i < 8; i++) {
            const angle = (i * 45 * Math.PI) / 180;
            coords.push([
              fLat + Math.cos(angle) * radM * mToLat,
              fLon + Math.sin(angle) * radM * mToLon
            ]);
          }
          await fetch(`${backendUrl}/api/v1/zones`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              name: name || (category === 'safe_zone' ? 'Зелена зона падіння' : 'Небезпечна зона (Місто)'),
              zone_type: category === 'safe_zone' ? 'safe' : 'danger',
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
          <h3>{isEditing ? 'РЕДАГУВАННЯ ОБ\'ЄКТА' : 'ДОДАВАННЯ ТАКТИЧНОГО ОБ\'ЄКТА'}</h3>
          <button onClick={onClose} className="btn-close"><X size={18} /></button>
        </div>

        <form onSubmit={handleSubmit}>
          {!isEditing && (
            <div className="form-group">
              <label>Тип об'єкта</label>
              <div className="category-grid">
                <button
                  type="button"
                  className={`cat-btn ${category === 'ew_node' ? 'active' : ''}`}
                  onClick={() => setCategory('ew_node')}
                >
                  <Radio size={16} color="#38bdf8" /> РЕБ (Спрямований)
                </button>
                <button
                  type="button"
                  className={`cat-btn ${category === 'camera' ? 'active' : ''}`}
                  onClick={() => setCategory('camera')}
                >
                  <Camera size={16} color="#34d399" /> Оптична камера
                </button>
                <button
                  type="button"
                  className={`cat-btn ${category === 'acoustic' ? 'active' : ''}`}
                  onClick={() => setCategory('acoustic')}
                >
                  <Mic size={16} color="#fbbf24" /> Акустичний пост
                </button>
                <button
                  type="button"
                  className={`cat-btn ${category === 'observation_post' ? 'active' : ''}`}
                  onClick={() => setCategory('observation_post')}
                >
                  <Eye size={16} color="#a78bfa" /> Пост спостереження
                </button>
                <button
                  type="button"
                  className={`cat-btn ${category === 'witness_report' ? 'active' : ''}`}
                  onClick={() => setCategory('witness_report')}
                >
                  <Users size={16} color="#f472b6" /> Очевидець
                </button>
                <button
                  type="button"
                  className={`cat-btn ${category === 'target_asset' ? 'active' : ''}`}
                  onClick={() => setCategory('target_asset')}
                >
                  <Target size={16} color="#f87171" /> Захищена ціль
                </button>
                <button
                  type="button"
                  className={`cat-btn ${category === 'danger_zone' ? 'active danger' : ''}`}
                  onClick={() => setCategory('danger_zone')}
                >
                  <ShieldAlert size={16} color="#ef4444" /> Червона зона
                </button>
                <button
                  type="button"
                  className={`cat-btn ${category === 'safe_zone' ? 'active safe' : ''}`}
                  onClick={() => setCategory('safe_zone')}
                >
                  <ShieldCheck size={16} color="#10b981" /> Зелена зона
                </button>
              </div>
            </div>
          )}

          <div className="form-group">
            <label>Позивний / Назва</label>
            <input
              type="text"
              placeholder="Наприклад: РЕБ-ГАРДА-2 або Сектор-Північ"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="tactical-input"
              required
            />
          </div>

          {category !== 'safe_zone' && category !== 'danger_zone' && (
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

          {!isEditing && (category === 'safe_zone' || category === 'danger_zone') && (
            <div className="form-group">
              <label>Радіус зони (м) для генерації периметру</label>
              <input
                type="number"
                value={zoneRadius}
                onChange={(e) => setZoneRadius(e.target.value)}
                className="tactical-input"
              />
            </div>
          )}

          <div className="modal-actions">
            <button type="button" onClick={onClose} className="btn-secondary">СКАСУВАТИ</button>
            <button type="submit" disabled={loading} className="btn-primary">
              {loading ? 'ЗБЕРЕЖЕННЯ...' : isEditing ? 'ОНОВИТИ ДАНІ' : 'РОЗМІСТИТИ НА КАРТІ'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};