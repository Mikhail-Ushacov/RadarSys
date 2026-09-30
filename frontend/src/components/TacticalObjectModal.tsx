import React, { useState, useEffect } from 'react';
import {
  Radio, Radar, Camera, Mic, Eye,
  Target, ShieldCheck, ShieldAlert, AlertTriangle
} from 'lucide-react';
import { EWNode, TacticalSensor, TacticalZone, SensorType, ZoneType } from '../types';
import { Modal } from './ui/Modal';
import { Button } from './ui/Button';
import styles from './TacticalObjectModal.module.css';

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
  | 'rf_24ghz'
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
  const [zoneRadius] = useState('1500');
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

  const cats: { id: ObjectCategory; icon: React.ReactNode; label: string }[] = [
    { id: 'ew_node', icon: <Radio size={15} />, label: 'РЕБ (Спрямований)' },
    { id: 'target_asset', icon: <Target size={15} />, label: "Критичний об'єкт" },
    { id: 'danger_zone', icon: <ShieldAlert size={15} />, label: 'Червона зона (No-drop)' },
    { id: 'caution_zone', icon: <AlertTriangle size={15} />, label: 'Помаранчева зона (Буфер)' },
    { id: 'safe_zone', icon: <ShieldCheck size={15} />, label: 'Зелена зона (Killbox)' },
    { id: 'camera', icon: <Camera size={15} />, label: 'Оптична камера' },
    { id: 'acoustic', icon: <Mic size={15} />, label: 'Акустичний пост' },
    { id: 'rf_24ghz', icon: <Radar size={15} />, label: 'RF сенсор 24 ГГц' },
    { id: 'observation_post', icon: <Eye size={15} />, label: 'Мобільна вогнева група' },
  ];

  return (
    <Modal
      title={isEditing ? "РЕДАГУВАННЯ ТАКТИЧНОГО ОБ'ЄКТА" : "СТВОРЕННЯ ТАКТИЧНОГО ОБ'ЄКТА / ЗОНИ"}
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>СКАСУВАТИ</Button>
          <Button variant="primary" onClick={(e) => { e.preventDefault(); handleSubmit(e as unknown as React.FormEvent); }} disabled={loading}>
            {loading ? 'ЗБЕРЕЖЕННЯ...' : isEditing ? 'ОНОВИТИ ДАНІ' : "ЗБЕРЕГТИ ОБ'ЄКТ В БД"}
          </Button>
        </>
      }
    >
      <form onSubmit={handleSubmit}>
        {!isEditing && (
          <div className={styles.group}>
            <span className={styles.label}>Тип об'єкта або тактичної зони</span>
            <div className={styles.catGrid}>
              {cats.map((c) => (
                <Button
                  key={c.id}
                  type="button"
                  variant="default"
                  active={category === c.id}
                  onClick={() => setCategory(c.id)}
                >
                  {c.icon} {c.label}
                </Button>
              ))}
            </div>
          </div>
        )}

        <div className={styles.group}>
          <label className={styles.label}>Позивний / Назва</label>
          <input
            type="text"
            placeholder={isZoneCategory ? 'Наприклад: Район Вишгородських лісів' : 'Наприклад: РЕБ-ГАРДА-2'}
            value={name}
            onChange={(e) => setName(e.target.value)}
            className={styles.input}
            required
          />
        </div>

        {isZoneCategory ? (
          <div className={styles.group}>
            <div className={`${styles.label} ${styles.labelRow}`}>
              <span>Координати вершин [Lat, Lon]</span>
              <span className="t-mono">
                {freeformCoordsText.split('\n').filter(l => l.trim()).length} вершин
              </span>
            </div>
            <textarea
              rows={5}
              className={`${styles.input} t-mono`}
              placeholder={'50.51234, 30.54321\n50.53456, 30.56789\n50.51987, 30.58912'}
              value={freeformCoordsText}
              onChange={(e) => setFreeformCoordsText(e.target.value)}
            />
            <div className={styles.hint}>
              Порада: також можна скористатись малюванням зони прямо на карті, щоб наклікати полігон.
            </div>
          </div>
        ) : (
          <div className={styles.coordsRow}>
            <div className={styles.group}>
              <label className={styles.label}>Широта (Lat)</label>
              <input
                type="number"
                step="any"
                value={lat}
                onChange={(e) => setLat(e.target.value)}
                className={`${styles.input} t-mono`}
                required
              />
            </div>
            <div className={styles.group}>
              <label className={styles.label}>Довгота (Lon)</label>
              <input
                type="number"
                step="any"
                value={lon}
                onChange={(e) => setLon(e.target.value)}
                className={`${styles.input} t-mono`}
                required
              />
            </div>
          </div>
        )}

        {category === 'ew_node' && (
          <>
            <div className={styles.coordsRow}>
              <div className={styles.group}>
                <label className={styles.label}>Азимут променя (°)</label>
                <input
                  type="number"
                  min="0"
                  max="360"
                  value={azimuth}
                  onChange={(e) => setAzimuth(e.target.value)}
                  className={`${styles.input} t-mono`}
                />
              </div>
              <div className={styles.group}>
                <label className={styles.label}>Ширина променя (°)</label>
                <input
                  type="number"
                  min="5"
                  max="120"
                  value={beamwidth}
                  onChange={(e) => setBeamwidth(e.target.value)}
                  className={`${styles.input} t-mono`}
                />
              </div>
            </div>
            <div className={styles.group}>
              <label className={styles.label}>Радіус дії (м)</label>
              <input
                type="number"
                value={radius}
                onChange={(e) => setRadius(e.target.value)}
                className={`${styles.input} t-mono`}
              />
            </div>
          </>
        )}

        {['camera', 'acoustic', 'rf_24ghz', 'observation_post', 'witness_report', 'target_asset'].includes(category) && (
          <>
            <div className={styles.group}>
              <label className={styles.label}>Радіус виявлення / засікання (м)</label>
              <input
                type="number"
                value={radius}
                onChange={(e) => setRadius(e.target.value)}
                className={`${styles.input} t-mono`}
              />
            </div>
            <div className={styles.group}>
              <label className={styles.label}>Опис / Додаткові дані</label>
              <input
                type="text"
                placeholder="Оптичний канал, частоти або контакт"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className={styles.input}
              />
            </div>
          </>
        )}
      </form>
    </Modal>
  );
};